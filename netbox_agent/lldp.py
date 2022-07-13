import logging
import subprocess

from netbox_agent.misc import is_tool


class LLDP():
    def __init__(self, output=None):
        if not is_tool('lldpctl'):
            logging.debug('lldpd package seems to be missing or daemon not running.')
        if output:
            self.output = output
        else:
            self.output = subprocess.getoutput('lldpctl -f keyvalue')
        self.data = self.parse()

    def parse(self):
        output_dict = {}
        vlans = {}
        vid = None
        for entry in self.output.splitlines():
            if '=' not in entry:
                continue
            path, value = entry.strip().split("=", 1)
            split_path = path.split(".")
            interface = split_path[1]
            path_components, final = split_path[:-1], split_path[-1]
            current_dict = output_dict
            print("DDDDDDDD")
            print(path, value)
            print(interface)
            print(path_components, final)
            print(current_dict)

            if vlans.get(interface) is None:
                vlans[interface] = {}

            vid = None
            for path_component in path_components:
                print("PPPPPPPPPPP")
                current_dict[path_component] = current_dict.get(path_component, {})
                current_dict = current_dict[path_component]
                print(current_dict)
                if 'vlan-id' in path:
                    vid = value
                    vlans[interface][value] = vlans[interface].get(vid, {})
                elif path.endswith('vlan'):
                    vid = value.replace('vlan-', '').replace('VLAN', '')
                    vlans[interface][vid] = vlans[interface].get(vid, {})
                elif 'pvid' in path and vid:
                    vlans[interface][vid]['pvid'] = True
            if 'vlan' not in path and final != "unknown-tlv":
                current_dict[final] = value
        for interface, vlan in vlans.items():
            output_dict['lldp'][interface]['vlan'] = vlan
        if not output_dict:
            logging.debug('No LLDP output, please check your network config.')
        return output_dict

    def get_switch_ip(self, interface):
        # lldp.eth0.chassis.mgmt-ip=100.66.7.222
        if 'lldp' not in self.data or self.data['lldp'].get(interface) is None:
            return None
        return self.data['lldp'][interface]['chassis'].get('mgmt-ip')

    def get_switch_port(self, interface):
        # lldp.eth0.port.descr=GigabitEthernet1/0/1
        if 'lldp' not in self.data or self.data['lldp'].get(interface) is None:
            return None
        if self.data['lldp'][interface]['port'].get('ifname'):
            return self.data['lldp'][interface]['port']['ifname']
        return self.data['lldp'][interface]['port'].get('descr')

    def get_switch_vlan(self, interface):
        # lldp.eth0.vlan.vlan-id=296
        if 'lldp' not in self.data or self.data['lldp'].get(interface) is None:
            return None
        return self.data['lldp'][interface].get('vlan')
