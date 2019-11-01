import gi
gi.require_version('BlockDev', '2.0')
from gi.repository import BlockDev, GLib

ps = BlockDev.PluginSpec()
ps.name = BlockDev.Plugin.LVM
ps.so_name = "libbd_lvm.so"

BlockDev.init([ps])
