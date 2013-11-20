from foris import gettext as _
from form import Password, Textbox, Dropdown, Checkbox, Hidden
import fapi
from nuci import client, filters
from nuci.modules.uci_raw import Uci, Config, Section, Option
from validators import LenRange
import validators


class BaseConfigHandler(object):
    def __init__(self, data=None):
        self.data = data
        self.__form_cache = None

    @property
    def form(self):
        if self.__form_cache is None:
            self.__form_cache = self.get_form()
        return self.__form_cache

    def call_action(self, action):
        """Call AJAX action.

        :param action:
        :return: dict of picklable AJAX results
        """
        raise NotImplementedError()

    def get_form(self):
        """Get form for this wizard. MUST be a single-section form.

        :return:
        :rtype: fapi.ForisForm
        """
        raise NotImplementedError()

    def save(self, extra_callbacks=None):
        """

        :param extra_callbacks: list of extra callbacks to call when saved
        :return:
        """
        form = self.form
        form.validate()
        if extra_callbacks:
            for cb in extra_callbacks:
                form.add_callback(cb)
        if form.valid:
            form.save()
            return True
        else:
            return False


class PasswordHandler(BaseConfigHandler):
    """
    Setting the password
    """
    def get_form(self):
        # form definitions
        pw_form = fapi.ForisForm("password", self.data)
        pw_main = pw_form.add_section(name="set_password", title=_("Password"),
                                      description=_("Welcome to the first start. Set your password for this administation site."
                                                    " The password must be at least 6 charaters long."))
        pw_main.add_field(Password, name="password", label=_("Password"), required=True,
                          validators=LenRange(6, 60))
        pw_main.add_field(Password, name="password_validation", label=_("Password (repeat)"))
        pw_form.add_validator(validators.FieldsEqual("password", "password_validation",
                                                     _("Passwords do not equal.")))

        def pw_form_cb(data):
            import pbkdf2
            # use 48bit pseudo-random salt internally generated by pbkdf2
            password = pbkdf2.crypt(data['password'], iterations=1000)

            uci = Uci()
            foris = Config("foris")
            uci.add(foris)
            auth = Section("auth", "config")
            foris.add(auth)
            auth.add(Option("password", password))

            return "edit_config", uci

        pw_form.add_callback(pw_form_cb)
        return pw_form


class WanHandler(BaseConfigHandler):
    def get_form(self):
        # WAN
        wan_form = fapi.ForisForm("wan", self.data, filter=filters.uci)
        wan_main = wan_form.add_section(name="set_wan", title=_("WAN"),
                                        description=_("TODO: write desc (wan mac)"))

        WAN_DHCP = "dhcp"
        WAN_STATIC = "static"
        WAN_PPPOE = "pppoe"
        WAN_OPTIONS = (
            (WAN_DHCP, _("DHCP")),
            (WAN_STATIC, _("Static")),
            (WAN_PPPOE, _("PPPoE")),
        )

        wan_main.add_field(Textbox, name="macaddr", label=_("MAC address"),
                           nuci_path="uci.network.wan.macaddr",
                           validators=validators.MacAddress())
        wan_main.add_field(Dropdown, name="proto", label=_("Protocol"),
                           nuci_path="uci.network.wan.proto",
                           args=WAN_OPTIONS, default=WAN_DHCP)
        wan_main.add_field(Checkbox, name="static_ipv6", label=_("Use IPv6"),
                           nuci_path="uci.network.wan.ip6addr",
                           nuci_preproc=lambda val: bool(val.value))\
            .requires("proto", WAN_STATIC)
        wan_main.add_field(Textbox, name="ipaddr", label=_("IP address"),
                           nuci_path="uci.network.wan.ipaddr",
                           required=True, validators=validators.IPv4())\
            .requires("proto", WAN_STATIC)\
            .requires("static_ipv6", False)
        wan_main.add_field(Textbox, name="netmask", label=_("Network mask"),
                           nuci_path="uci.network.wan.netmask",
                           required=True, validators=validators.IPv4())\
            .requires("proto", WAN_STATIC)\
            .requires("static_ipv6", False)
        wan_main.add_field(Textbox, name="gateway", label=_("Gateway"),
                           nuci_path="uci.network.wan.gateway",
                           validators=validators.IPv4())\
            .requires("proto", WAN_STATIC)\
            .requires("static_ipv6", False)

        wan_main.add_field(Textbox, name="username", label=_("DSL user"),
                           nuci_path="uci.network.wan.username",)\
            .requires("proto", WAN_PPPOE)
        wan_main.add_field(Textbox, name="password", label=_("DSL password"),
                           nuci_path="uci.network.wan.password",)\
            .requires("proto", WAN_PPPOE)
        wan_main.add_field(Checkbox, name="ppp_ipv6", label=_("Enable IPv6"),
                           nuci_path="uci.network.wan.ipv6",
                           nuci_preproc=lambda val: bool(int(val.value)))\
            .requires("proto", WAN_PPPOE)

        wan_main.add_field(Textbox, name="ip6addr", label=_("IPv6 address"),
                           nuci_path="uci.network.wan.ip6addr")\
            .requires("static_ipv6", True)
        wan_main.add_field(Textbox, name="ip6gw", label=_("IPv6 gateway"),
                           nuci_path="uci.network.wan.ip6gw")\
            .requires("static_ipv6", True)
        wan_main.add_field(Textbox, name="ip6prefix", label=_("IPv6 prefix"),
                           nuci_path="uci.network.wan.ip6prefix")\
            .requires("static_ipv6", True)

        def wan_form_cb(data):
            uci = Uci()
            config = Config("network")
            uci.add(config)

            wan = Section("wan", "interface")
            config.add(wan)
            wan.add(Option("macaddr", data['macaddr']))
            wan.add(Option("proto", data['proto']))
            if data['proto'] == WAN_PPPOE:
                wan.add(Option("username", data['username']))
                wan.add(Option("password", data['password']))
                wan.add(Option("ipv6", data['ppp_ipv6']))
            elif data.get("static_ipv6") is True:
                wan.add(Option("ip6addr", data['ip6addr']))
                wan.add(Option("ip6gw", data['ip6gw']))
                wan.add(Option("ip6prefix", data['ip6prefix']))
                # remove ipv4 settings
                wan.add_removal(Option("ipaddr", None))
                wan.add_removal(Option("netmask", None))
                wan.add_removal(Option("gateway", None))
            elif data['proto'] == WAN_STATIC:
                wan.add(Option("ipaddr", data['ipaddr']))
                wan.add(Option("netmask", data['netmask']))
                wan.add(Option("gateway", data['gateway']))
                # remove ipv6 settings
                wan.add_removal(Option("ip6addr", None))
                wan.add_removal(Option("ip6gw", None))
                wan.add_removal(Option("ip6prefix", None))

            return "edit_config", uci

        wan_form.add_callback(wan_form_cb)

        return wan_form


class TimeHandler(BaseConfigHandler):
    def _action_ntp_update(self):
        return client.ntp_update()

    def call_action(self, action):
        """Call AJAX action.

        :param action:
        :return: dict of picklable AJAX results
        """
        if action == "ntp_update":
            ntp_ok = self._action_ntp_update()
            return dict(success=ntp_ok)
        elif action == "time_form":
            if hasattr(self, 'render') and callable(self.render):
                # only if the subclass implements render
                return dict(success=True, form=self.render(is_xhr=True))
        raise ValueError("Unknown Wizard action.")

    def get_form(self):
        time_form = fapi.ForisForm("time", self.data, filter=filters.time)
        time_main = time_form.add_section(name="set_time", title=_("Time"),
                                          description=_("TODO: write desc (time setup)"))

        time_main.add_field(Textbox, name="time", label=_("Time"), nuci_path="time",
                            nuci_preproc=lambda v: v.local)

        def time_form_cb(data):
            client.set_time(data['time'])
            return "none", None

        time_form.add_callback(time_form_cb)

        return time_form


class LanHandler(BaseConfigHandler):
    def get_form(self):
        lan_form = fapi.ForisForm("lan", self.data, filter=filters.uci)
        lan_main = lan_form.add_section(name="set_lan", title=_("LAN"),
                                        description=_("Most users don't need to change these settings."))

        lan_main.add_field(Textbox, name="dhcp_subnet", label=_("Router IP address"),
                           nuci_path="uci.network.lan.ipaddr",
                           hint="Also defines the range of assigned IP addresses.")
        lan_main.add_field(Checkbox, name="dhcp_enabled", label=_("Enable DHCP"),
                           nuci_path="uci.dhcp.lan.ignore",
                           nuci_preproc=lambda val: not bool(int(val.value)), default=True)
        lan_main.add_field(Textbox, name="dhcp_min", label=_("DHCP min"),
                           nuci_path="uci.dhcp.lan.start")\
            .requires("dhcp_enabled", True)
        lan_main.add_field(Textbox, name="dhcp_max", label=_("DHCP max"),
                           nuci_path="uci.dhcp.lan.limit")\
            .requires("dhcp_enabled", True)

        def lan_form_cb(data):
            uci = Uci()
            config = Config("dhcp")
            uci.add(config)

            dhcp = Section("lan", "dhcp")
            config.add(dhcp)
            if data['dhcp_enabled']:
                dhcp.add(Option("ignore", "0"))
                dhcp.add(Option("start", data['dhcp_min']))
                dhcp.add(Option("limit", data['dhcp_max']))
                network = Config("network")
                uci.add(network)
                interface = Section("lan", "interface")
                network.add(interface)
                interface.add(Option("ipaddr", data['dhcp_subnet']))
            else:
                dhcp.add(Option("ignore", "1"))

            return "edit_config", uci

        lan_form.add_callback(lan_form_cb)

        return lan_form


class WifiHandler(BaseConfigHandler):
    def get_form(self):
        wifi_form = fapi.ForisForm("wifi", self.data, filter=filters.uci)
        wifi_main = wifi_form.add_section(name="set_wifi", title=_("WiFi"),
                                          description=_("TODO: write desc (wifi)"))
        wifi_main.add_field(Hidden, name="iface_section", nuci_path="uci.wireless.@wifi-iface[0]",
                            nuci_preproc=lambda val: val.name)
        wifi_main.add_field(Checkbox, name="wifi_enabled", label=_("Enable WiFi"), default=True,
                            nuci_path="uci.wireless.@wifi-iface[0].disabled",
                            nuci_preproc=lambda val: not bool(int(val.value)))
        wifi_main.add_field(Textbox, name="ssid", label=_("Network name"),
                            nuci_path="uci.wireless.@wifi-iface[0].ssid",
                            validators=validators.LenRange(1, 32))\
            .requires("wifi_enabled", True)
        wifi_main.add_field(Checkbox, name="ssid_hidden", label=_("Hide SSID"), default=False,
                            nuci_path="uci.wireless.@wifi-iface[0].hidden",
                            hint=_("If set, network is not visible when scanning for available networks."))\
            .requires("wifi_enabled", True)
        wifi_main.add_field(Dropdown, name="channel", label=_("Network channel"), default="1",
                            args=((str(i), str(i)) for i in range(1, 13)),
                            nuci_path="uci.wireless.radio0.channel")\
            .requires("wifi_enabled", True)
        wifi_main.add_field(Textbox, name="key", label=_("Network password"),
                            nuci_path="uci.wireless.@wifi-iface[0].key",
                            hint=_("WPA2 preshared key, that is required to connect to the network."))\
            .requires("wifi_enabled", True)

        def wifi_form_cb(data):
            uci = Uci()
            wireless = Config("wireless")
            uci.add(wireless)

            iface = Section(data['iface_section'], "wifi-iface")
            wireless.add(iface)
            device = Section("radio0", "wifi-device")
            wireless.add(device)
            # we must toggle both wifi-iface and device
            iface.add(Option("disabled", not data['wifi_enabled']))
            device.add(Option("disabled", not data['wifi_enabled']))
            if data['wifi_enabled']:
                iface.add(Option("ssid", data['ssid']))
                iface.add(Option("hidden", data['ssid_hidden']))
                iface.add(Option("encryption", "psk2+tkip+aes"))  # TODO: find in docs
                iface.add(Option("key", data['key']))
                # channel is in wifi-device section
                device.add(Option("channel", data['channel']))
            else:
                pass  # wifi disabled

            return "edit_config", uci

        wifi_form.add_callback(wifi_form_cb)

        return wifi_form


class SystemPasswordHandler(BaseConfigHandler):
    """
    Setting the password of a system user (currently only root's pw).
    """
    def get_form(self):
        system_pw_form = fapi.ForisForm("system_password", self.data)
        system_pw_main = system_pw_form.add_section(name="set_password",
                                                    title=_("Advanced administration"),
                                                    description=_(
                                                        "To access the advanced administration, you must set root user's password. "
                                                        "When the password is set, follow the link below."))
        system_pw_main.add_field(Password, name="password", label=_("Password"), required=True)
        system_pw_main.add_field(Password, name="password_validation", label=_("Password (repeat)"))
        system_pw_form.add_validator(validators.FieldsEqual("password", "password_validation",
                                                            _("Passwords do not equal.")))

        def system_pw_form_cb(data):
            client.set_password("root", data["password"])
            return "none", None

        system_pw_form.add_callback(system_pw_form_cb)
        return system_pw_form
