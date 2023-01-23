# for localized messages
from . import _

description = _("Scans for services and creates a bouquet")

from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigInteger, ConfigClock, ConfigSubDict
from Components.NimManager import nimmanager
from Plugins.Plugin import PluginDescriptor
from Tools.BoundFunction import boundFunction

# for satellite
from .satscanlcn import SatScanLcn, SatScanLcn_Setup, getConfiguredSats
from .providers import PROVIDERS

# for terrestrial
from .TerrestrialScan_Setup import TerrestrialScan_Setup

configured_sats = getConfiguredSats()

# satellite options
config.plugins.satscanlcn = ConfigSubsection()
config.plugins.satscanlcn.provider = ConfigSelection(choices = [(x, PROVIDERS[x]["name"]) for x in sorted(PROVIDERS.keys(), key=lambda k: k.lower()) if PROVIDERS[x]["transponder"]["orbital_position"] in configured_sats])
config.plugins.satscanlcn.extensions = ConfigYesNo(default = False)
config.plugins.satscanlcn.hd_only = ConfigYesNo(default = False)
config.plugins.satscanlcn.fta_only = ConfigYesNo(default = False)

for x in PROVIDERS.keys(): # if any provider has a regions list write it to a ConfigSelection 
	if "bat" in PROVIDERS[x] and "bat_regions" in PROVIDERS[x]["bat"]:
		setattr(config.plugins.satscanlcn, "bat-regions-" + x, ConfigSelection(choices=[(a, a) for a in sorted(PROVIDERS[x]["bat"]["bat_regions"].keys())]))
	if "nit" in PROVIDERS[x] and "BouquetIDs" in PROVIDERS[x]["nit"]:
		setattr(config.plugins.satscanlcn, "nit-BouquetIDs-" + x, ConfigSelection(choices=[(a, a) for a in sorted(PROVIDERS[x]["nit"]["BouquetIDs"].keys())]))

# advanced options
config.plugins.satscanlcn.extra_debug = ConfigYesNo(default = False)
config.plugins.satscanlcn.sync_with_known_tps = ConfigYesNo(default = False)
config.plugins.satscanlcn.force_service_name = ConfigYesNo(default = False)

# terrestrial options
config.plugins.TerrestrialScan = ConfigSubsection()
config.plugins.TerrestrialScan.networkid_bool = ConfigYesNo(default=False)
config.plugins.TerrestrialScan.networkid = ConfigInteger(default=0, limits=(0, 65535))
config.plugins.TerrestrialScan.clearallservices = ConfigYesNo(default=True)
config.plugins.TerrestrialScan.onlyfree = ConfigYesNo(default=True)
config.plugins.TerrestrialScan.skipT2 = ConfigYesNo(default=False)
uhf_vhf_choices = [
			('uhf', _("UHF Europe complete")),
			('uhf_short', _("UHF Europe channels 21-49")),
			('uhf_vhf', _("UHF/VHF Europe")),
			('australia', _("Australia generic"))]
if nimmanager.getTerrestrialsList(): # check transponders are available from terrestrial.xml
	uhf_vhf_choices.append(('xml', _("From XML")))
config.plugins.TerrestrialScan.uhf_vhf = ConfigSelection(default='uhf', choices=uhf_vhf_choices)
config.plugins.TerrestrialScan.makebouquet = ConfigYesNo(default=True)
config.plugins.TerrestrialScan.makeradiobouquet = ConfigYesNo(default=False)
config.plugins.TerrestrialScan.makexmlfile = ConfigYesNo(default=False)
config.plugins.TerrestrialScan.lcndescriptor = ConfigSelection(default=0x83, choices=[
			(0x83, "0x83"),
			(0x87, "0x87")])
config.plugins.TerrestrialScan.channel_list_id = ConfigInteger(default=0, limits=(0, 65535))
config.plugins.TerrestrialScan.stabliseTime = ConfigSelection(default=2, choices=[(i, "%d" % i) for i in range(2, 11)])


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

def TerrestrialScanStart(menuid, **kwargs):
	if menuid == "scan" and nimmanager.getEnabledNimListOfType("DVB-T"):
		return [(_("Terrestrial Scan"), TerrestrialScanMain, "TerrestrialScan_Setup", 75, True)]
	return []

def TerrestrialScanMain(session, close=None, **kwargs):
	session.openWithCallback(boundFunction(SatScanLcnCallback, close), TerrestrialScan_Setup)

def Plugins(**kwargs):
	plist = []
	if nimmanager.hasNimType("DVB-S"):
		plist.append( PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_MENU, needsRestart = False, fnc=SatScanLcnStart) )
		if config.plugins.satscanlcn.extensions.getValue():
			plist.append(PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=startdownload, needsRestart=True))
	else:
		print("[SatScanLcn] No DVB-S tuner available so don't load")
	if nimmanager.hasNimType("DVB-T"):
		plist.append(PluginDescriptor(name=_("Terrestrial Scan"), description="For scanning terrestrial tv", where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=TerrestrialScanStart))
	else:
		print("[TerrestrialScan] No DVB-T tuner available so don't load")
	return plist
