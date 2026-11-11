"""Adaptation code: compose unchanged Store with its instrumented tool boundary."""
import atexit
import importlib
import importlib.util
import sys
from adapter import adapt

_PACKAGE = '_policy_labcluster'

def modules(path):
    if _PACKAGE not in sys.modules:
        from tools.upstream_checkout import adapted_checkout
        dependency=adapted_checkout(path); checkout=dependency.__enter__()
        atexit.register(dependency.__exit__,None,None,None)
        spec=importlib.util.spec_from_file_location(_PACKAGE,checkout/'core/__init__.py',submodule_search_locations=[str(checkout/'core')])
        module=importlib.util.module_from_spec(spec);sys.modules[_PACKAGE]=module;spec.loader.exec_module(module)
    return tuple(importlib.import_module(_PACKAGE+'.'+name) for name in ('tools','tracing','schemas','store','messaging'))

class Application:
    def __init__(self,upstream,bundle=None):
        tools,tracing,self.schemas,storage,messaging=modules(upstream)
        self.store=storage.Store();self.store.initialize()
        try:self.policy=adapt(bundle=bundle)
        except BaseException:
            self.store.close();raise
        self.store.policy=self.policy;self.runtime=self.policy.runtime
        self.trace=tracing.Trace(self.store);self._tools=tools.Tools;self._closed=False
        self.bus=messaging.Bus(self.trace)
    def tools(self,principal):return self._tools(principal,self.store,self.trace)
    @property
    def effect_calls(self):return self.runtime.effect_calls
    def close(self):
        if not self._closed:
            self.runtime.close();self.store.close();self._closed=True

def load_upstream(path,bundle=None):return Application(path,bundle)
