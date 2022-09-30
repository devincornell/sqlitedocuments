from __future__ import annotations
import dataclasses
import datetime
import psutil

from doctable.util.unit_format import format_memory
from ..util import format_memory, format_time

@dataclasses.dataclass
class Step:
    _msg: str
    i: int
    ts: datetime# = dataclasses.field(default_factory=datetime.now)
    mem: int# = dataclasses.field(default_factory=lambda: psutil.virtual_memory().used)

    @classmethod
    def now(cls, i: int = None, msg: str = None, pid: int = None) -> Step:
        '''Create a new step based on current timestamp/memory usage.'''
        pid = pid if pid is not None else os.getpid()
        return cls(
            i = i,
            msg = msg,
            ts = datetime.datetime.now(),
            mem = psutil.Process(pid).memory_info()#psutil.virtual_memory(),
        )

    @property
    def msg(self):
        return self._msg if self._msg is not None else '.'

    def __sub__(self, other: Step):
        return self.ts_diff(other)

    def ts_diff(self, other: Step):
        return (self.ts - other.ts).total_seconds()

    def format(self, prev_step: Step = None, show_ts=True, show_delta=True, show_mem=True):
        if show_ts:
            ts_str = f"{self.ts.strftime('%a %H:%M:%S')}/"
        else:
            ts_str = ''

        if show_mem:
            mem_usage = f"{format_memory(self.mem):>9}/"
        else:
            mem_usage = ''

        if show_delta:
            if prev_step is not None:
                ts_diff = f"+{format_time(self.ts_diff(prev_step)):>10}/"
            else:
                ts_diff = f'{" "*11}/'
        else:
            ts_diff = ''

        return f'{ts_str}{mem_usage}{ts_diff}{self.i:2}: {self.msg}'
        
        