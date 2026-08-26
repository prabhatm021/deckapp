"""Top-bar tray icon, spoken straight over D-Bus.

GNOME shows tray icons through the StatusNotifierItem protocol (the
AppIndicator extension). The usual libraries for it are GTK3-only and cannot
share a process with GTK4, so DeckApp implements the two interfaces itself:

    org.kde.StatusNotifierItem   the icon
    com.canonical.dbusmenu       its menu

Nothing here imports Gtk, so the tray keeps running with no windows open.
"""
import logging
import os

from gi.repository import Gio, GLib

logger = logging.getLogger(__name__)

WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus"><arg type="s" name="status"/></signal>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="ItemActivationRequested">
      <arg type="i" name="id"/>
      <arg type="u" name="timestamp"/>
    </signal>
  </interface>
</node>
"""


class MenuItem:
    def __init__(self, item_id, label, on_click=None, separator=False,
                 enabled=True, icon_name=None, icon_data=None):
        self.id = item_id
        self.label = label
        self.on_click = on_click
        self.separator = separator
        self.enabled = enabled
        self.icon_name = icon_name
        self.icon_data = icon_data

    def properties(self):
        if self.separator:
            return {"type": GLib.Variant("s", "separator")}
        props = {
            "label": GLib.Variant("s", self.label),
            "enabled": GLib.Variant("b", self.enabled),
            "visible": GLib.Variant("b", True),
        }
        if self.icon_data:
            # Raw PNG: the shell renders it as-is, with no theme lookup and
            # no recolouring of the kind *-symbolic names get.
            props["icon-data"] = GLib.Variant("ay", self.icon_data)
        elif self.icon_name:
            props["icon-name"] = GLib.Variant("s", self.icon_name)
        return props


class TrayIcon:
    """A status icon whose menu is rebuilt each time it is opened."""

    def __init__(self, app_id, title, icon_name, build_menu, on_activate=None,
                 icon_theme_path=""):
        self.app_id = app_id
        self.title = title
        self.icon_name = icon_name
        self.icon_theme_path = icon_theme_path
        self.build_menu = build_menu          # () -> list[MenuItem]
        self.on_activate = on_activate        # left click on the icon

        self.bus = None
        self.bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._owner_id = 0
        self._item_reg = 0
        self._menu_reg = 0
        self._items = []
        self._revision = 1
        self.available = False

    # ── Lifecycle ──

    def start(self) -> bool:
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            logger.warning("No session bus, tray unavailable: %s", e)
            return False

        self._owner_id = Gio.bus_own_name_on_connection(
            self.bus, self.bus_name, Gio.BusNameOwnerFlags.NONE,
            self._on_name_acquired, self._on_name_lost,
        )
        return True

    def stop(self):
        for registration in (self._item_reg, self._menu_reg):
            if registration:
                self.bus.unregister_object(registration)
        self._item_reg = self._menu_reg = 0
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0
        self.available = False

    def _on_name_acquired(self, connection, _name):
        item_info = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]

        self._item_reg = connection.register_object(
            ITEM_PATH, item_info, self._item_call, self._item_get, None
        )
        self._menu_reg = connection.register_object(
            MENU_PATH, menu_info, self._menu_call, self._menu_get, None
        )
        self._register_with_watcher()

    def _on_name_lost(self, _connection, _name):
        logger.warning("Lost the tray bus name")
        self.available = False

    def _register_with_watcher(self):
        def _done(source, result, _data=None):
            try:
                source.call_finish(result)
                self.available = True
                logger.info("Tray icon registered")
            except GLib.Error as e:
                logger.warning(
                    "No tray host to register with (%s). On GNOME this needs "
                    "the AppIndicator extension.", e.message,
                )

        self.bus.call(
            WATCHER_NAME, WATCHER_PATH, WATCHER_NAME,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self.bus_name,)),
            None, Gio.DBusCallFlags.NONE, 3000, None, _done,
        )

    # ── StatusNotifierItem ──

    def _item_get(self, _conn, _sender, _path, _iface, prop, *_extra):
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", self.app_id),
            "Title": GLib.Variant("s", self.title),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", self.icon_name),
            "IconThemePath": GLib.Variant("s", self.icon_theme_path),
            "AttentionIconName": GLib.Variant("s", ""),
            "OverlayIconName": GLib.Variant("s", ""),
            "ToolTip": GLib.Variant("(sa(iiay)ss)",
                                    (self.icon_name, [], self.title, "")),
            "Menu": GLib.Variant("o", MENU_PATH),
            "ItemIsMenu": GLib.Variant("b", True),
        }
        return values.get(prop)

    def _item_call(self, _conn, _sender, _path, _iface, method, _params,
                   invocation, *_extra):
        if method in ("Activate", "SecondaryActivate") and self.on_activate:
            self.on_activate()
        invocation.return_value(None)

    # ── DBus menu ──

    def _menu_get(self, _conn, _sender, _path, _iface, prop, *_extra):
        return {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }.get(prop)

    def _refresh_items(self):
        self._items = self.build_menu()
        return self._items

    def _find(self, item_id):
        return next((item for item in self._items if item.id == item_id), None)

    def _layout(self):
        children = [
            GLib.Variant("(ia{sv}av)", (item.id, item.properties(), []))
            for item in self._items
        ]
        root_props = {"children-display": GLib.Variant("s", "submenu")}
        return GLib.Variant("(ia{sv}av)", (0, root_props, children))

    def _menu_call(self, _conn, _sender, _path, _iface, method, params,
                   invocation, *_extra):
        if method == "GetLayout":
            self._refresh_items()
            invocation.return_value(GLib.Variant.new_tuple(
                GLib.Variant("u", self._revision), self._layout()
            ))

        elif method == "GetGroupProperties":
            ids = params.unpack()[0]
            wanted = [item for item in self._items
                      if not ids or item.id in ids]
            invocation.return_value(GLib.Variant(
                "(a(ia{sv}))",
                ([(item.id, item.properties()) for item in wanted],),
            ))

        elif method == "GetProperty":
            item_id, name = params.unpack()[:2]
            item = self._find(item_id)
            value = item.properties().get(name) if item else None
            invocation.return_value(
                GLib.Variant("(v)", (value or GLib.Variant("s", ""),))
            )

        elif method == "Event":
            item_id, event_id = params.unpack()[:2]
            if event_id == "clicked":
                item = self._find(item_id)
                if item is not None and item.on_click is not None:
                    GLib.idle_add(item.on_click)
            invocation.return_value(None)

        elif method == "EventGroup":
            for item_id, event_id, _data_, _time in params.unpack()[0]:
                if event_id == "clicked":
                    item = self._find(item_id)
                    if item is not None and item.on_click is not None:
                        GLib.idle_add(item.on_click)
            invocation.return_value(GLib.Variant("(ai)", ([],)))

        elif method == "AboutToShow":
            before = [(item.id, item.label) for item in self._items]
            self._refresh_items()
            changed = before != [(item.id, item.label) for item in self._items]
            if changed:
                self._revision += 1
                self.bus.emit_signal(
                    None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                    GLib.Variant("(ui)", (self._revision, 0)),
                )
            invocation.return_value(GLib.Variant("(b)", (changed,)))

        else:
            invocation.return_value(None)

    # ── Updates ──

    def menu_changed(self):
        """Tell the shell the menu contents changed."""
        self._revision += 1
        if self.bus is not None:
            self.bus.emit_signal(
                None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                GLib.Variant("(ui)", (self._revision, 0)),
            )
