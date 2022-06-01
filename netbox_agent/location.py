import os
import importlib
import importlib.machinery

from netbox_agent.config import config


class LocationBase():
    """
    This class is used to guess the location in order to push the information
    in Netbox for a `Device`

    A driver takes a `value` and evaluates a regex with a `capture group`.

    There's embeded drivers such as `file` or `cmd` which read a file or return the
    output of a file.

    There's also a support for an external driver file outside of this project in case
    the logic isn't supported here.
    """

    def __init__(self, value):
        self.value = value

    def __init__(self, driver, driver_value, driver_file, regex, *args, **kwargs):
        self.driver = driver
        self.driver_value = driver_value
        self.driver_file = driver_file
        self.regex = regex

        self.value = None

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
        if self.value is None:
            if self.driver is None:
                return None
            if not hasattr(self.driver, 'get'):
                raise Exception(
                    "Your driver {} doesn't have a get() function, please fix it".format(self.driver)
                )
            return getattr(self.driver, 'get')(self.driver_value, self.regex)
        else:
            return self.value


class Tenant(LocationBase):
    def __init__(self):
        driver = config.tenant.driver.split(':')[0] if \
            config.tenant.driver else None
        driver_value = ':'.join(config.tenant.driver.split(':')[1:]) if \
            config.tenant.driver else None
        driver_file = config.tenant.driver_file
        regex = config.tenant.regex

        #if driver and driver_value and driver_file and regex:
        super().__init__(driver, driver_value, driver_file, regex)
        #else:
        #    super().__init__(os.environ['NETBOX_TENANT'])


class Datacenter(LocationBase):
    def __init__(self):
        driver = config.datacenter.driver.split(':')[0] if \
            config.datacenter.driver else None
        driver_value = ':'.join(config.datacenter.driver.split(':')[1:]) if \
            config.datacenter.driver else None
        driver_file = config.datacenter.driver_file
        regex = config.datacenter.regex

        #if driver and driver_value and driver_file and regex:
        super().__init__(driver, driver_value, driver_file, regex)
        #else:
        #super().__init__(os.environ['HOSTNAME'])


class Location(LocationBase):
    def __init__(self):
        driver = config.location.driver.split(':')[0] if \
            config.location.driver else None
        driver_value = ':'.join(config.location.driver.split(':')[1:]) if \
            config.location.driver else None
        driver_file = config.location.driver_file
        regex = config.location.regex

        #if driver and driver_value and driver_file and regex:
        super().__init__(driver, driver_value, driver_file, regex)
        #else:
        #    super().__init__(os.environ['NETBOX_LOCATION'])


class Rack(LocationBase):
    def __init__(self):
        driver = config.rack.driver.split(':')[0] if \
            config.rack.driver else None
        driver_value = ':'.join(config.rack.driver.split(':')[1:]) if \
            config.rack.driver else None
        driver_file = config.rack.driver_file
        regex = config.rack.regex

        #if driver and driver_value and driver_file and regex:
        super().__init__(driver, driver_value, driver_file, regex)
        #else:
        #    super().__init__(os.environ['NETBOX_RACK'])


class Slot(LocationBase):
    def __init__(self):
        driver = config.slot.driver.split(':')[0] if \
            config.slotn.driver else None
        driver_value = ':'.join(config.slot.driver.split(':')[1:]) if \
            config.slot.driver else None
        driver_file = config.slot.driver_file
        regex = config.slot.regex

        #if driver and driver_value and driver_file and regex:
        super().__init__(driver, driver_value, driver_file, regex)
        #else:
        #    super().__init__(os.environ['NETBOX_SLOT'])
