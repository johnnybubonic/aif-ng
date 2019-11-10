import gi
gi.require_version('NM', '2.0')
from gi.repository import NM, GLib

NM.ensure_init([None])


def addBDPlugin(plugin_name):
    plugins = NM.get_available_plugin_names()
    plugins.append(plugin_name)
    plugins = list(set(plugins))  # Deduplicate
    spec = NM.plugin_specs_from_names(plugins)
    return(NM.ensure_init(spec))
