import netbox_agent.dmidecode as dmidecode
from netbox_agent.config import config
from netbox_agent.config import netbox_instance as nb
from netbox_agent.inventory import Inventory
from netbox_agent.inputdriver import InputDriver
from netbox_agent.misc import create_netbox_tags, get_device_role, get_device_type, get_device_platform
from netbox_agent.network import ServerNetwork
from netbox_agent.power import PowerSupply
from pprint import pprint
import subprocess
import logging
import socket
import sys


class ServerBase():
    def __init__(self, dmi=None):
        if dmi:
            self.dmi = dmi
        else:
            self.dmi = dmidecode.parse()

        self.baseboard = dmidecode.get_by_type(self.dmi, 'Baseboard')
        self.bios = dmidecode.get_by_type(self.dmi, 'BIOS')
        self.chassis = dmidecode.get_by_type(self.dmi, 'Chassis')
        self.system = dmidecode.get_by_type(self.dmi, 'System')

        generic_service_tags = ["1234567890", "0123456789", "123456789", "System Serial Number", "empty"]

        service_tag = self.get_service_tag()
        if "suncave" in self.get_hostname():
            self.system[0]['Serial Number'] = self.get_hostname()
        elif service_tag in generic_service_tags:
            self.network = ServerNetwork(server=self)
            self.system[0]['Serial Number'] = self.network.get_ipmi()['mac']

        self.device_platform = get_device_platform(config.device.platform)

        self.network = None

        self.tags = list(set([
            x.strip() for x in config.device.tags.split(',') if x.strip()
        ])) if config.device.tags else []
        self.nb_tags = list(create_netbox_tags(self.tags))
        config_cf = set([
            f.strip() for f in config.device.custom_fields.split(",")
            if f.strip()
        ])
        self.custom_fields = {}
        self.custom_fields.update(dict([
            (k.strip(), v.strip()) for k, v in
            [f.split("=", 1) for f in config_cf]
        ]))

    def get_tenant(self):
        tenant = InputDriver("tenant")
        return tenant.get()

    def get_netbox_tenant(self):
        tenant = self.get_tenant()
        if tenant is None:
            return None
        slug = tenant.lower().replace(" ", "-")
        nb_tenant = nb.tenancy.tenants.get(
            slug=self.get_tenant()
        )
        return nb_tenant

    def get_site(self):
        site = InputDriver("site")
        return site.get()

    def get_netbox_site(self):
        site = self.get_site()
        if site is None:
            logging.error("Specifying a Site is mandatory in Netbox")
            sys.exit(1)

        name = site.replace("-", " ")
        slug = site.lower().replace(" ", "-")
        nb_site = nb.dcim.sites.get(slug=slug)

        if nb_site is None:
            logging.error("Creating Site {name}. Remember to set the Region.".format(name=name))
            nb.dcim.sites.create(name=name, slug=slug, status="active")

        return nb_site

    def update_netbox_location(self, server):
        nb_rack = self.get_netbox_rack()
        nb_site = self.get_netbox_site()

        update = False
        if server.site != nb_site:
            old_nb_site = server.site

            logging.info('Site location has changed from {} to {}, updating'.format(
                server.site.slug,
                nb_site.slug,
            ))
            update = True
            server.site = nb_site

            nb.dcim.devices.update([{
                "id": server.id,
                "site": server.site.id if server.site is not None else None
            }])

            if old_nb_site is not None:
                old_nb_site = nb.dcim.sites.get(slug=old_nb_site.slug)

                if old_nb_site.device_count == 0:
                    logging.info("Deleting Site: {name}".format(name=old_nb_site.name))
                    nb.dcim.sites.delete([old_nb_site.id])

        if server.rack != nb_rack:
            old_nb_rack = server.rack

            logging.info('Rack location has changed from {} to {}, updating'.format(
                server.rack,
                nb_rack,
            ))
            update = True
            server.rack = nb_rack

            nb.dcim.devices.update([{
                "id": server.id,
                "rack": server.rack.id if server.rack is not None else None
            }])

            if nb_rack is None:
                server.face = None
                server.position = None

            if old_nb_rack is not None:
                old_nb_rack = nb.dcim.racks.get(
                    name=old_nb_rack,
                    site_id=old_nb_rack.site.id,
                )

                if old_nb_rack.device_count == 0:
                    logging.info("Deleting Rack: {name}".format(name=old_nb_rack))
                    nb.dcim.racks.delete([old_nb_rack.id])

        nb_location = self.get_netbox_location()
        if (
            nb_rack is None
            and server.location != nb_location
        ):
            old_nb_location = server.location

            logging.info('Location has changed from {} to {}'.format(
                server.location.name if server.location is not None else None,
                nb_location.name if nb_location is not None else None
            ))

            update = True
            server.location = nb_location

            nb.dcim.devices.update([{
                "id": server.id,
                "location": server.location.id if server.location is not None else None
            }])

            if old_nb_location is not None:
                old_nb_location = nb.dcim.locations.get(
                    name=old_nb_location,
                    site_id=old_nb_location.site.id,
                )

                if old_nb_location.rack_count == 0 and old_nb_location.device_count == 0:
                    logging.info("Deleting Location: {name}".format(name=old_nb_location))
                    nb.dcim.locations.delete([old_nb_location.id])

        device_type = nb.dcim.device_types.get(
            id=server.device_type.id
        )

        height = self.get_rack_height()
        if height and device_type.u_height != height:
            logging.info("Changing device type {name} height from {old_height} to {new_height}".format(
                name=device_type.name,
                old_height=device_type.u_height,
                new_height=height
            ))
            nb.dcim.device_type.update([{
                "id": device_type.id,
                "u_height": height
            }])


        return update, server

    def update_netbox_expansion_location(self, server, expansion):
        update = False
        if expansion.tenant != server.tenant:
            expansion.tenant = server.tenant
            update = True
        if expansion.site != server.site:
            expansion.site = server.site
            update = True
        if expansion.rack != server.rack:
            expansion.rack = server.rack
            update = True
        return update

    def get_location(self):
        location = InputDriver("location")
        return location.get()

    def get_netbox_location(self):
        location = self.get_location()
        site = self.get_netbox_site()
        if not location:
            return None
        if location and not site:
            logging.error("Can't get location if no site is configured or found")
            sys.exit(1)

        name = location.replace("-", " ")
        slug = location.lower().replace(" ", "-")

        nb_location = nb.dcim.locations.get(
            name=name,
            site_id=site.id,
        )

        if nb_location is None:
            nb_location = nb.dcim.locations.create(
                name=name,
                slug=slug,
                site=site.id
            )

        return nb_location

    def get_rack(self):
        rack = InputDriver("rack")
        return rack.get()

    def get_netbox_rack(self):
        rack = self.get_rack()
        site = self.get_netbox_site()
        if not rack:
            return None
        if rack and not site:
            logging.error("Can't get rack if no site is configured or found")
            sys.exit(1)

        name = rack.replace("-", " ")

        nb_rack = nb.dcim.racks.get(
            name=name,
            site_id=site.id,
        )

        nb_location = self.get_netbox_location()
        if nb_rack is None:
            nb_rack = nb.dcim.racks.create(
                name=name,
                site=site.id,
                location=nb_location.id if nb_location is not None else None
            )
        elif nb_location is not None and nb_location != nb_rack.location:
            old_nb_location = nb_rack.location

            logging.info("Updating Rack: name = {name}, id = {id}".format(name=nb_rack.name, id=nb_rack.id))
            nb_rack = nb.dcim.racks.update([{"id": nb_rack.id, "location": nb_location.id}])[0]

            old_nb_location = nb.dcim.locations.get(
                name=old_nb_location,
                site_id=old_nb_location.site.id,
            )

            if old_nb_location.rack_count == 0 and old_nb_location.device_count == 0:
                logging.info("Deleting Location: name = {name}, id = {id}".format(
                    name=old_nb_location,
                    id=old_nb_location.id
                ))
                nb.dcim.locations.delete([old_nb_location.id])

        return nb_rack

    def get_position(self):
        position = InputDriver("position")
        return position.get()

    def get_face(self):
        face = InputDriver("face")
        return face.get()

    def get_rack_height(self):
        height = InputDriver("height").get()

        try:
            height = int(height)
            if height < 0:
                raise ValueError("Height must be greater than 0. Height value was {}".format(height))
        except TypeError:
            return None

        return height


    def get_product_name(self):
        """
        Return the Chassis Name from dmidecode info
        """
        return self.system[0]['Product Name'].strip()

    def get_service_tag(self):
        """
        Return the Service Tag from dmidecode info
        """
        return self.system[0]['Serial Number'].strip()

    def get_expansion_service_tag(self):
        """
        Return the virtual Service Tag from dmidecode info host
        with 'expansion'
        """
        return self.system[0]['Serial Number'].strip() + " expansion"

    def get_hostname(self):
        if config.hostname_cmd is None:
            return '{}'.format(socket.gethostname())
        return subprocess.getoutput(config.hostname_cmd)

    def is_blade(self):
        raise NotImplementedError

    def get_blade_slot(self):
        raise NotImplementedError

    def get_chassis(self):
        raise NotImplementedError

    def get_chassis_name(self):
        raise NotImplementedError

    def get_chassis_service_tag(self):
        raise NotImplementedError

    def get_bios_version(self):
        raise NotImplementedError

    def get_bios_version_attr(self):
        raise NotImplementedError

    def get_bios_release_date(self):
        raise NotImplementedError

    def get_power_consumption(self):
        raise NotImplementedError

    def get_expansion_product(self):
        raise NotImplementedError

    def _netbox_create_chassis(self, site, tenant, rack):
        device_type = get_device_type(self.get_chassis())
        device_role = get_device_role(config.device.chassis_role)
        serial = self.get_chassis_service_tag()
        position = self.get_position()
        face = self.get_face()
        logging.info('Creating chassis blade (serial: {serial})'.format(
            serial=serial))
        new_chassis = nb.dcim.devices.create(
            name=self.get_chassis_name(),
            device_type=device_type.id,
            serial=serial,
            device_role=device_role.id,
            site=site.id if site else None,
            tenant=tenant.id if tenant else None,
            rack=rack.id if rack else None,
            position=position,
            face=face,
            tags=[{'name': x} for x in self.tags],
            custom_fields=self.custom_fields,
        )
        return new_chassis

    def _netbox_create_blade(self, chassis, site, tenant, rack):
        device_role = get_device_role(config.device.blade_role)
        device_type = get_device_type(self.get_product_name())
        serial = self.get_service_tag()
        hostname = self.get_hostname()
        position = self.get_position()
        face = self.get_face()
        logging.info(
            'Creating blade (serial: {serial}) {hostname} on chassis {chassis_serial}'.format(
                serial=serial, hostname=hostname, chassis_serial=chassis.serial
            ))
        new_blade = nb.dcim.devices.create(
            name=hostname,
            serial=serial,
            device_role=device_role.id,
            device_type=device_type.id,
            parent_device=chassis.id,
            site=site.id if site else None,
            tenant=tenant.id if tenant else None,
            rack=rack.id if rack else None,
            position=position,
            face=face,
            tags=[{'name': x} for x in self.tags],
            custom_fields=self.custom_fields,
        )
        return new_blade

    def _netbox_create_blade_expansion(self, chassis, site, tenant, rack):
        device_role = get_device_role(config.device.blade_role)
        device_type = get_device_type(self.get_expansion_product())
        serial = self.get_expansion_service_tag()
        hostname = self.get_hostname() + " expansion"
        position = self.get_position()
        face = self.get_face()
        logging.info(
            'Creating expansion (serial: {serial}) {hostname} on chassis {chassis_serial}'.format(
                serial=serial, hostname=hostname, chassis_serial=chassis.serial
            ))
        new_blade = nb.dcim.devices.create(
            name=hostname,
            serial=serial,
            device_role=device_role.id,
            device_type=device_type.id,
            parent_device=chassis.id,
            site=site.id if site else None,
            tenant=tenant.id if tenant else None,
            rack=rack.id if rack else None,
            position=position,
            face=face,
            tags=[{'name': x} for x in self.tags],
        )
        return new_blade

    def _netbox_deduplicate_server(self):
        serial = self.get_service_tag()
        hostname = self.get_hostname()
        server = nb.dcim.devices.get(name=hostname)
        if server and server.serial != serial:
            server.delete()

    def _netbox_create_server(self, site, tenant, rack):
        device_role = get_device_role(config.device.server_role)
        device_type = get_device_type(self.get_product_name())
        nb_location = self.get_netbox_location()
        position = self.get_position()
        face = self.get_face()
        location = nb_location.id if nb_location is not None else None
        if rack is not None:
            if rack.location is not None:
                location = rack.location.id
            else:
                location = None

        if not device_type:
            raise Exception('Chassis "{}" doesn\'t exist'.format(self.get_chassis()))
        serial = self.get_service_tag()
        hostname = self.get_hostname()
        logging.info('Creating server (serial: {serial}) {hostname}'.format(
            serial=serial, hostname=hostname))
        new_server = nb.dcim.devices.create(
            name=hostname,
            serial=serial,
            device_role=device_role.id,
            device_type=device_type.id,
            platform=self.device_platform,
            site=site.id if site else None,
            tenant=tenant.id if tenant else None,
            location=location,
            rack=rack.id if rack else None,
            position=position,
            face=face,
            tags=[{'name': x} for x in self.tags],
        )
        return new_server

    def _netbox_update_server(self, server_id, site, tenant):
        device_role = get_device_role(config.device.server_role)
        device_type = get_device_type(self.get_product_name())
        position = self.get_position()
        face = self.get_face()
        if not device_type:
            raise Exception('Chassis "{}" doesn\'t exist'.format(self.get_chassis()))
        serial = self.get_service_tag()
        hostname = self.get_hostname()
        logging.info('Updating server (serial: {serial}) {hostname}'.format(
            serial=serial, hostname=hostname))
        new_server = nb.dcim.devices.update([{
            "id": server_id,
            "name": hostname,
            "serial": serial,
            "device_role": device_role.id,
            "device_type": device_type.id,
            "platform": self.device_platform,
            "site": site.id if site else None,
            "position": position,
            "face": face,
            "tenant": tenant.id if tenant else None,
            "tags": [{'name': x} for x in self.tags]
        }])
        return new_server[0]

    def get_netbox_server(self, expansion=False):
        if expansion is False:
            return nb.dcim.devices.get(serial=self.get_service_tag())
        else:
            return nb.dcim.devices.get(serial=self.get_expansion_service_tag())

    def _netbox_set_or_update_blade_slot(self, server, chassis, site):
        # before everything check if right chassis
        actual_device_bay = server.parent_device.device_bay \
                if server.parent_device else None
        actual_chassis = actual_device_bay.device \
                if actual_device_bay else None
        slot = self.get_blade_slot()
        if actual_chassis and \
           actual_chassis.serial == chassis.serial and \
           actual_device_bay.name == slot:
            return

        real_device_bays = nb.dcim.device_bays.filter(
            device_id=chassis.id,
            name=slot,
        )
        real_device_bays = nb.dcim.device_bays.filter(
            device_id=chassis.id,
            name=slot,
        )
        if real_device_bays:
            logging.info(
                'Setting device ({serial}) new slot on {slot} '
                '(Chassis {chassis_serial})..'.format(
                    serial=server.serial, slot=slot, chassis_serial=chassis.serial
                ))
            # reset actual device bay if set
            if actual_device_bay:
                # Forces the evaluation of the installed_device attribute to
                # workaround a bug probably due to lazy loading optimization
                # that prevents the value change detection
                actual_device_bay.installed_device
                actual_device_bay.installed_device = None
                actual_device_bay.save()
            # setup new device bay
            real_device_bay = next(real_device_bays)
            real_device_bay.installed_device = server
            real_device_bay.save()
        else:
            logging.error('Could not find slot {slot} for chassis'.format(
                slot=slot
            ))

    def _netbox_set_or_update_blade_expansion_slot(self, expansion, chassis, site):
        # before everything check if right chassis
        actual_device_bay = expansion.parent_device.device_bay if expansion.parent_device else None
        actual_chassis = actual_device_bay.device if actual_device_bay else None
        slot = self.get_blade_expansion_slot()
        if actual_chassis and \
           actual_chassis.serial == chassis.serial and \
           actual_device_bay.name == slot:
            return

        real_device_bays = nb.dcim.device_bays.filter(
            device_id=chassis.id,
            name=slot,
        )
        if not real_device_bays:
            logging.error('Could not find slot {slot} expansion for chassis'.format(
                slot=slot
            ))
            return
        logging.info(
            'Setting device expansion ({serial}) new slot on {slot} '
            '(Chassis {chassis_serial})..'.format(
                serial=expansion.serial, slot=slot, chassis_serial=chassis.serial
            ))
        # reset actual device bay if set
        if actual_device_bay:
            # Forces the evaluation of the installed_device attribute to
            # workaround a bug probably due to lazy loading optimization
            # that prevents the value change detection
            actual_device_bay.installed_device
            actual_device_bay.installed_device = None
            actual_device_bay.save()
        # setup new device bay
        real_device_bay = next(real_device_bays)
        real_device_bay.installed_device = expansion
        real_device_bay.save()

    def netbox_create_or_update(self, config):
        """
        Netbox method to create or update info about our server/blade

        Handle:
        * new chassis for a blade
        * new slot for a blade
        * hostname update
        * Network infos
        * Inventory management
        * PSU management
        """
        site = self.get_netbox_site()
        rack = self.get_netbox_rack()
        tenant = self.get_netbox_tenant()

        if config.purge_old_devices:
            self._netbox_deduplicate_server()

        if self.is_blade():
            chassis = nb.dcim.devices.get(
                serial=self.get_chassis_service_tag()
            )
            # Chassis does not exist
            if not chassis:
                chassis = self._netbox_create_chassis(site, tenant, rack)

            server = nb.dcim.devices.get(serial=self.get_service_tag())
            if not server:
                server = self._netbox_create_blade(chassis, site, tenant, rack)

            # Set slot for blade
            self._netbox_set_or_update_blade_slot(server, chassis, site)
        else:
            server = nb.dcim.devices.get(serial=self.get_service_tag())
            if not server:
                server = self._netbox_create_server(site, tenant, rack)


        logging.debug('Updating Server...')
        # check network cards
        if config.register or config.update_all or config.update_network:
            self.network = ServerNetwork(server=self)
            self.network.create_or_update_netbox_network_cards()
        update_inventory = config.inventory and (config.register or
                config.update_all or config.update_inventory)
        # update inventory if feature is enabled
        self.inventory = Inventory(server=self)
        if update_inventory:
            self.inventory.create_or_update()
        # update psu
        if config.register or config.update_all or config.update_psu:
            self.power = PowerSupply(server=self)
            self.power.create_or_update_power_supply()
            self.power.report_power_consumption()

        expansion = nb.dcim.devices.get(serial=self.get_expansion_service_tag())
        if self.own_expansion_slot() and config.expansion_as_device:
            logging.debug('Update Server expansion...')
            if not expansion:
                expansion = self._netbox_create_blade_expansion(chassis, site, tenant, rack)

            # set slot for blade expansion
            self._netbox_set_or_update_blade_expansion_slot(expansion, chassis, site)
            if update_inventory:
                # Updates expansion inventory
                inventory = Inventory(server=self, update_expansion=True)
                inventory.create_or_update()
        elif self.own_expansion_slot() and expansion:
            expansion.delete()
            expansion = None

        update = 0
        # for every other specs
        # check hostname
        if server.name != self.get_hostname():
            server.name = self.get_hostname()
            update += 1

        server_tags = sorted(set([x.name for x in server.tags]))
        tags = sorted(set(self.tags))
        if server_tags != tags:
            new_tags_ids = [x.id for x in self.nb_tags]
            if not config.preserve_tags:
                server.tags = new_tags_ids
            else:
                server_tags_ids = [x.id for x in server.tags]
                server.tags = sorted(set(new_tags_ids + server_tags_ids))
            update += 1

        if server.custom_fields != self.custom_fields:
            server.custom_fields = self.custom_fields
            update += 1

        if config.update_all or config.update_location:
            ret, server = self.update_netbox_location(server)
            update += ret

        if config.update_all:
            server = self._netbox_update_server(server.id, site, tenant)
            update += True

        if server.platform != self.device_platform:
            server.platform = self.device_platform
            update += 1

        if update:
            server.save()

        if expansion:
            update = 0
            expansion_name = server.name + ' expansion'
            if expansion.name != expansion_name:
                expansion.name = expansion_name
                update += 1
            if self.update_netbox_expansion_location(server, expansion):
                update += 1
            if update:
                expansion.save()
        logging.debug('Finished updating Server!')

    def print_debug(self):
        self.network = ServerNetwork(server=self)
        print('Site:', self.get_site())
        print('Netbox Site:', self.get_netbox_site())
        print('Rack:', self.get_rack())
        print('Netbox Rack:', self.get_netbox_rack())
        print('Is blade:', self.is_blade())
        print('Got expansion:', self.own_expansion_slot())
        print('Product Name:', self.get_product_name())
        print('Platform:', self.device_platform)
        print('Chassis:', self.get_chassis())
        print('Chassis service tag:', self.get_chassis_service_tag())
        print('Service tag:', self.get_service_tag())
        print('NIC:',)
        pprint(self.network.get_network_cards())
        pass

    def own_expansion_slot(self):
        """
        Indicates if the device hosts an expansion card
        """
        return False

    def own_gpu_expansion_slot(self):
        """
        Indicates if the device hosts a GPU expansion card
        """
        return False

    def own_drive_expansion_slot(self):
        """
        Indicates if the device hosts a drive expansion bay
        """
        return False
