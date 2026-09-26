"""Transient errors belong to the notebook loop, not background threads."""

import asyncio
import weakref


class ErrorTimeoutMixin:
    _error_timeout = None

    def schedule_error_clear(self, delay):
        """Replace the previous timeout without keeping this model alive."""
        self.cancel_error_timeout()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Outside a running notebook/event loop, leave the error visible.
            return

        model_ref = weakref.ref(self)

        def clear():
            model = model_ref()
            if model is not None:
                model._error_timeout = None
                model.clear_error_message()

        self._error_timeout = loop.call_later(delay, clear)

    def cancel_error_timeout(self):
        if self._error_timeout is not None:
            self._error_timeout.cancel()
            self._error_timeout = None

    def clear_error_message(self):
        self.cancel_error_timeout()
        self.error_message = ""
