# for localized messages
from . import _

description = _("Scans for services and creates a bouquet")

from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigNumber, NoSave, ConfigClock, ConfigEnableDisable, ConfigSubDict
from Components.NimManager import nimmanager
from Plugins.Plugin import PluginDescriptor
from Tools.BoundFunction import boundFunction

from .satscanlcn import SatScanLcn, SatScanLcn_Setup, getConfiguredSats
from .providers import PROVIDERS

configured_sats = getConfiguredSats()

config.plugins.satscanlcn = ConfigSubsection()
config.plugins.satscanlcn.provider = ConfigSelection(choices = [(x, PROVIDERS[x]["name"]) for x in sorted(PROVIDERS.keys()) if PROVIDERS[x]["transponder"]["orbital_position"] in configured_sats])
config.plugins.satscanlcn.extensions = ConfigYesNo(default = False)

for x in PROVIDERS.keys(): # if any provider has a regions list write it to a ConfigSelection 
	if "bat" in PROVIDERS[x] and "bat_regions" in PROVIDERS[x]["bat"]:
		setattr(config.plugins.satscanlcn, x, ConfigSelection(choices=[(a, a) for a in sorted(PROVIDERS[x]["bat"]["bat_regions"].keys())]))

config.plugins.satscanlcn.extra_debug = ConfigYesNo(default = False)
config.plugins.satscanlcn.sync_with_known_tps = ConfigYesNo(default = False)
config.plugins.satscanlcn.force_service_name = ConfigYesNo(default = False)


def startdownload(session, **kwargs): # Called from extensions menu if this option is active
	session.open(SatScanLcn)

def SatScanLcnStart(menuid, **kwargs): # Menu position of plugin setup screen
	if menuid == "scan":
		return [(_("SatScanLcn"), SatScanLcnMain, "SatScanLcn_Setup", 11, True)]
	return []

def SatScanLcnMain(session, close=None, **kwargs): # calls setup screen
	session.openWithCallback(boundFunction(SatScanLcnCallback, close), SatScanLcn_Setup)

def SatScanLcnCallback(close=None, answer=None): # Called on exiting setup screen. Should force a recursive close on a succsssful scan.
	if close and answer:
		close(True)

def Plugins(**kwargs):
	plist = []
	if nimmanager.hasNimType("DVB-S"):
		plist.append( PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_MENU, needsRestart = False, fnc=SatScanLcnStart) )
		if config.plugins.satscanlcn.extensions.getValue():
			plist.append(PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=startdownload, needsRestart=True))
	return plist
