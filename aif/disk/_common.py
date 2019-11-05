import gi
gi.require_version('BlockDev', '2.0')
from gi.repository import BlockDev, GLib

BlockDev.ensure_init([None])


def addBDPlugin(plugin_name):
    plugins = BlockDev.get_available_plugin_names()
    plugins.append(plugin_name)
    plugins = list(set(plugins))  # Deduplicate
    spec = BlockDev.plugin_specs_from_names(plugins)
    return(BlockDev.ensure_init(spec))
