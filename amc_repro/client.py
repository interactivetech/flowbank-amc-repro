import asyncio
import os
import time
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError
from .storage import response_preview


@dataclass
class Settings:
    temperature: float = 0
    top_p: float = 1
    seed: int | None = 42
    max_tokens: int = 4096
    thinking: str = 'off'
    concurrency: int = 1
    requests_per_minute: float = 30
    timeout: float = 180
    retries: int = 3


class Client:
    def __init__(self, settings, progress=None):
        load_dotenv()
        self.settings = settings
        self.progress = progress
        self.api = AsyncOpenAI(base_url=os.environ['OPENAI_BASE_URL'], api_key=os.environ['OPENAI_API_KEY'],
                               timeout=settings.timeout, max_retries=0)
        self.model = None
        self.models = None
        self.sem = asyncio.Semaphore(settings.concurrency)
        self.rate_lock = asyncio.Lock()
        self.next_request = 0

    async def discover(self):
        self.models = (await self.api.models.list()).model_dump(mode='json')
        ids = [m['id'] for m in self.models['data']]
        requested = os.getenv('OPENAI_MODEL')
        if requested:
            if requested not in ids: raise ValueError('OPENAI_MODEL not in /models')
            self.model = requested
        elif len(ids) == 1:
            self.model = ids[0]
        else:
            raise ValueError(f'Set OPENAI_MODEL to one of the discovered IDs: {ids}')
        return self.models

    def parameters(self):
        s = self.settings
        params = dict(model=self.model, temperature=s.temperature, top_p=s.top_p, max_tokens=s.max_tokens)
        if s.seed is not None: params['seed'] = s.seed
        if s.thinking != 'default':
            if self.model and 'deepseek' in self.model.lower():
                params['extra_body'] = {'thinking': {'type': 'enabled' if s.thinking == 'on' else 'disabled'}}
            else:
                params['extra_body'] = {'chat_template_kwargs': {'enable_thinking': s.thinking == 'on'}}
        return params

    def metadata(self):
        return {'base_url': str(self.api.base_url), 'model': self.model, 'request_parameters': self.parameters(),
                'client_settings': asdict(self.settings), 'models_response': self.models}

    async def call(self, prompt, stage, operator, trace):
        params = self.parameters()
        common = trace.common
        position = ''
        if common.get('evaluation_index') and common.get('evaluation_total'):
            position = f"[{common['evaluation_index']}/{common['evaluation_total']}] "
        label = f"{position}{common.get('question_id', '?')} {common.get('workflow_id', '?')} {stage}"
        for attempt in range(self.settings.retries + 1):
            start = time.monotonic()
            try:
                if self.progress:
                    self.progress(f'{label} request {attempt + 1}/{self.settings.retries + 1}')
                async with self.sem:
                    async with self.rate_lock:
                        await asyncio.sleep(max(0, self.next_request - time.monotonic()))
                        self.next_request = time.monotonic() + 60 / self.settings.requests_per_minute
                    response = await self.api.chat.completions.create(messages=[{'role':'user','content':prompt}], **params)
                raw = response.model_dump(mode='json')
                output = response.choices[0].message.content or ''
                trace.emit(event='llm_call', stage_id=stage, operator_type=operator, attempt=attempt,
                           parameters=params, input=prompt, output=output, raw_response=raw,
                           usage=raw.get('usage'), latency=time.monotonic()-start, status='success')
                if self.progress:
                    usage = raw.get('usage') or {}
                    elapsed = time.monotonic() - start
                    finish = response.choices[0].finish_reason or 'unknown'
                    self.progress(f'{label} response tokens={usage.get("completion_tokens", "?")} '
                                  f'elapsed={elapsed:.1f}s finish={finish}: {response_preview(output)}')
                return output
            except (APIConnectionError, APITimeoutError, APIStatusError) as exc:
                status = getattr(exc, 'status_code', None)
                trace.emit(event='llm_call', stage_id=stage, operator_type=operator, attempt=attempt,
                           parameters=params, input=prompt, output=None, status='error', error=str(exc),
                           latency=time.monotonic()-start)
                if self.progress:
                    self.progress(f'{label} request error type={type(exc).__name__} status={status or "unknown"}')
                if status in (401,403) or (status and status < 500 and status != 429) or attempt == self.settings.retries:
                    raise
                await asyncio.sleep(min(30, 2 ** attempt))
