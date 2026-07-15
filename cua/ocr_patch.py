"""Patch RapidOCR's ONNX session creation to support DirectML GPU."""
import rapidocr_onnxruntime.utils as _utils
from onnxruntime import get_available_providers

_original_init = _utils.OrtInferSession.__init__


def _patched_init(self, config):
    """Patched init that injects DML provider before CPU fallback."""
    _original_init(self, config)

    dml_ep = "DmlExecutionProvider"
    if dml_ep in get_available_providers():
        # Check if DML is already being used (it shouldn't be, since RapidOCR
        # only checks for CUDA, not DML)
        current = self.session.get_providers()
        if dml_ep not in current:
            # Re-create the session with DML preferred
            from onnxruntime import (
                GraphOptimizationLevel,
                InferenceSession,
                SessionOptions,
            )

            sess_opt = SessionOptions()
            sess_opt.log_severity_level = 4
            sess_opt.enable_cpu_mem_arena = False
            sess_opt.graph_optimization_level = (
                GraphOptimizationLevel.ORT_ENABLE_ALL
            )

            providers = [
                (dml_ep, {}),
                ("CPUExecutionProvider", {"arena_extend_strategy": "kSameAsRequested"}),
            ]
            self.session = InferenceSession(
                config["model_path"],
                sess_options=sess_opt,
                providers=providers,
            )


_utils.OrtInferSession.__init__ = _patched_init
