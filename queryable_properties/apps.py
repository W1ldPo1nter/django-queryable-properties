# -*- coding: utf-8 -*-
from .compat import AppConfig


class QueryablePropertiesConfig(AppConfig or object):
    name = 'queryable_properties'
    ready_callbacks = []  #: Callbacks to run when the app registry is ready.

    @classmethod
    def add_ready_callback(cls, callback):
        """
        Register a callback that should run when Django's app registry is
        ready.

        Allows individual parts of the code to contribute setup code that must
        be executed when Django is done with initialization.

        :param function callback: The callback to register. Must be able to be
                                  called without arguments.
        """
        cls.ready_callbacks.append(callback)

    def ready(self):
        for callback in self.ready_callbacks:
            callback()
