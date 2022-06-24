import os
import importlib
import importlib.machinery

from netbox_agent.config import config


class InputDriver:
    """
    This class is used to guess the location in order to push the information
    in Netbox for a `Device`

    A driver takes a `value` and evaluates a regex with a `capture group`.

    There's embeded drivers such as `file` or `cmd` which read a file or return the
    output of a file.

    There's also a support for an external driver file outside of this project in case
    the logic isn't supported here.
    """

    def __init__(self, input_type):
        argument = None
        if input_type == "region":
            argument = config.height
        elif input_type == "site":
            argument = config.height
        elif input_type == "location":
            argument = config.height
        elif input_type == "rack":
            argument = config.height
        elif input_type == "position":
            argument = config.height
        elif input_type == "face":
            argument = config.height
        elif input_type == "tenant":
            argument = config.height
        elif input_type == "height":
            argument = config.height

        if not argument:
            raise Exception("Invalid input type: {}".format(input_type))

        self.driver = argument.driver.split(':')[0] if \
            argument.driver else None
        self.driver_value = ':'.join(argument.driver.split(':')[1:]) if \
            argument.driver else None
        self.driver_file = argument.driver_file
        self.regex = argument.regex

        if self.driver_file:
            try:
                # FIXME: Works with Python 3.3+, support older version?
                loader = importlib.machinery.SourceFileLoader('driver_file', self.driver_file)
                self.driver = loader.load_module()
            except ImportError:
                raise ImportError("Couldn't import {} as a module".format(self.driver_file))
        else:
            if self.driver:
                try:
                    self.driver = importlib.import_module(
                        'netbox_agent.drivers.{}'.format(self.driver)
                    )
                except ImportError:
                    raise ImportError("Driver {} doesn't exists".format(self.driver))

    def get(self):
        if self.driver is None:
            return None
        if not hasattr(self.driver, 'get'):
            raise Exception(
                "Your driver {} doesn't have a get() function, please fix it".format(self.driver)
            )
        return getattr(self.driver, 'get')(self.driver_value, self.regex)