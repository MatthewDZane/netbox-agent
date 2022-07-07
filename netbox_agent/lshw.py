from netbox_agent.misc import is_tool
import subprocess
import logging
import json
import sys


class LSHW():
    def __init__(self):
        if not is_tool('lshw'):
            logging.error('lshw does not seem to be installed')
            sys.exit(1)

        data = subprocess.getoutput(
            'lshw -quiet -json'
        )
        data = data.replace("\"#\\\"", "\"#\\\\\"")
        json_data = json.loads(data)
        # Starting from version 02.18, `lshw -json` wraps its result in a list
        # rather than returning directly a dictionary
        if isinstance(json_data, list):
            self.hw_info = json_data[0]
        else:
            self.hw_info = json_data
        self.info = {}
        self.memories = []
        self.interfaces = []
        self.cpus = []
        self.power = []
        self.disks = []
        self.gpus = []
        self.vendor = self.hw_info["vendor"]
        self.product = self.hw_info["product"]
        self.chassis_serial = self.hw_info["serial"]
        self.motherboard_serial = self.hw_info["children"][0].get("serial", "No S/N")
        self.motherboard = self.hw_info["children"][0].get("product", "Motherboard")

        self.find_inventory_items(self.hw_info)

    def get_hw_linux(self, hwclass):
        if hwclass == "cpu":
            return self.cpus
        if hwclass == "gpu":
            return self.gpus
        if hwclass == "network":
            return self.interfaces
        if hwclass == 'storage':
            return self.disks
        if hwclass == 'memory':
            return self.memories

    def find_network(self, obj):
        # Some interfaces do not have device (logical) name (eth0, for
        # instance), such as not connected network mezzanine cards in blade
        # servers. In such situations, the card will be named `unknown[0-9]`.
        unkn_intfs = []
        for i in self.interfaces:
            if type(i["name"]) == list:
                i["name"] = i["name"][0]

            if i["name"].startswith("unknown"):
                unkn_intfs.append(i)

        if obj["description"] != "Ethernet controller":
            unkn_name = "unknown{}".format(len(unkn_intfs))
            self.interfaces.append({
                "name": obj.get("logicalname", unkn_name),
                "macaddress": obj.get("serial", ""),
                "serial": obj.get("serial", ""),
                "product": obj["product"],
                "vendor": obj["vendor"],
                "description": obj["description"],
            })

    def find_storage(self, obj):
        if "children" in obj:
            for device in obj["children"]:
                self.disks.append({
                    "logicalname": device.get("logicalname"),
                    "product": device.get("product"),
                    "serial": device.get("serial"),
                    "version": device.get("version"),
                    "size": device.get("size"),
                    "description": device.get("description"),
                    "type": device.get("description"),
                })
        elif "configuration" not in obj or "driver" not in obj["configuration"]:
            return
        elif "nvme" in obj["configuration"]["driver"]:
            if not is_tool('nvme'):
                logging.error('nvme-cli >= 1.0 does not seem to be installed')
                return
            try:
                nvme = json.loads(
                    subprocess.check_output(
                        ["nvme", '-list', '-o', 'json'],
                        encoding='utf8')
                )
                for device in nvme["Devices"]:
                    d = {
                        'logicalname': device["DevicePath"],
                        'product': device["ModelNumber"],
                        'serial': device["SerialNumber"],
                        "version": device["Firmware"],
                        'description': "NVMe",
                        'type': "NVMe",
                    }
                    if "UsedSize" in device:
                        d['size'] = device["UsedSize"]
                    if "UsedBytes" in device:
                        d['size'] = device["UsedBytes"]
                    self.disks.append(d)
            except Exception:
                pass

    def find_cpus(self, obj):
        if "product" in obj:
            self.cpus.append({
                "product": obj["product"],
                "vendor": obj["vendor"],
                "description": obj["description"],
                "location": obj["slot"],
            })

    def find_memories(self, obj):
        if "children" not in obj:
            # print("not a DIMM memory.")
            return

        for dimm in obj["children"]:
            if "empty" in dimm["description"]:
                continue

            self.memories.append({
                "slot": dimm.get("slot"),
                "description": dimm.get("description"),
                "id": dimm.get("id"),
                "serial": dimm.get("serial", 'N/A'),
                "vendor": dimm.get("vendor", 'N/A'),
                "product": dimm.get("product", 'N/A'),
                "size": dimm.get("size", 0) / 2 ** 20 / 1024,
            })

    def find_gpus(self, obj):
        if "product" in obj:
            self.gpus.append({
                "product": obj["product"],
                "vendor": obj["vendor"],
                "description": obj["description"],
            })

    def find_inventory_items(self, obj):
        try:
            if obj["class"] == "generic":
                return
            elif obj["class"] == "power":
                self.power.append(obj)
            elif obj["class"] == "storage":
                self.find_storage(obj)
            elif obj["class"] == "memory":
                self.find_memories(obj)
            elif obj["class"] == "processor":
                self.find_cpus(obj)
            elif obj["class"] == "network":
                self.find_network(obj)
            elif obj["class"] == "display":
                self.find_gpus(obj)
        except KeyError:
            pass

        if "children" in obj:
            for child in obj["children"]:
                self.find_inventory_items(child)


if __name__ == "__main__":
    pass
