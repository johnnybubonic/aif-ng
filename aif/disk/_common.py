import logging
##
import gi
gi.require_version('BlockDev', '2.0')
from gi.repository import BlockDev, GLib

BlockDev.ensure_init([None])

_logger = logging.getLogger('disk:_common')


def addBDPlugin(plugin_name):
    _logger.info('Enabling plugin: {0}'.format(plugin_name))
    plugins = BlockDev.get_available_plugin_names()
    plugins.append(plugin_name)
    plugins = list(set(plugins))  # Deduplicate
    _logger.debug('Currently loaded plugins: {0}'.format(','.join(plugins)))
    spec = BlockDev.plugin_specs_from_names(plugins)
    _logger.debug('Plugin {0} loaded.'.format(plugin_name))
    return(BlockDev.ensure_init(spec))
