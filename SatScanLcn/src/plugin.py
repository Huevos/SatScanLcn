# for localized messages
from . import _

description = _("Scans for services and creates a bouquet")

from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigInteger, ConfigClock, ConfigSubDict
from Components.NimManager import nimmanager
from Plugins.Plugin import PluginDescriptor
from Tools.BoundFunction import boundFunction

# for satellite
from .satscanlcn import SatScanLcn, SatScanLcn_Setup, getConfiguredSats
from .satscanlcn_providers import PROVIDERS as SATSCANLCN_PROVIDERS

# for terrestrial
from .TerrestrialScan_Setup import TerrestrialScan_Setup

# for misplslcnscan
from .misplslcnscan_providers import PROVIDERS as MISPLSLCNSCAN_PROVIDERS
from .MisPlsLcnScan_Setup import MisPlsLcnScan_Setup

configured_sats = getConfiguredSats()

# satellite options
config.plugins.satscanlcn = ConfigSubsection()
config.plugins.satscanlcn.provider = ConfigSelection(choices = [(x, SATSCANLCN_PROVIDERS[x]["name"]) for x in sorted(SATSCANLCN_PROVIDERS.keys(), key=lambda k: k.lower()) if SATSCANLCN_PROVIDERS[x]["transponder"]["orbital_position"] in configured_sats])
config.plugins.satscanlcn.extensions = ConfigYesNo(default = False)
config.plugins.satscanlcn.hd_only = ConfigYesNo(default = False)
config.plugins.satscanlcn.fta_only = ConfigYesNo(default = False)

for x in SATSCANLCN_PROVIDERS.keys(): # if any provider has a regions list write it to a ConfigSelection 
	if "bat" in SATSCANLCN_PROVIDERS[x] and "bat_regions" in SATSCANLCN_PROVIDERS[x]["bat"]:
		setattr(config.plugins.satscanlcn, "bat-regions-" + x, ConfigSelection(choices=[(a, a) for a in sorted(SATSCANLCN_PROVIDERS[x]["bat"]["bat_regions"].keys())]))
	if "nit" in SATSCANLCN_PROVIDERS[x] and "BouquetIDs" in SATSCANLCN_PROVIDERS[x]["nit"]:
		setattr(config.plugins.satscanlcn, "nit-BouquetIDs-" + x, ConfigSelection(choices=[(a, a) for a in sorted(SATSCANLCN_PROVIDERS[x]["nit"]["BouquetIDs"].keys())]))

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

# MisPlsLcnScan options
config.plugins.MisPlsLcnScan = ConfigSubsection()
config.plugins.MisPlsLcnScan.provider = ConfigSelection(default="fransat_5W", choices=[(x, MISPLSLCNSCAN_PROVIDERS[x]["name"]) for x in sorted(MISPLSLCNSCAN_PROVIDERS.keys())])
config.plugins.MisPlsLcnScan.clearallservices = ConfigYesNo(default=False)
config.plugins.MisPlsLcnScan.onlyfree = ConfigYesNo(default=True)


def startdownload(session, **kwargs): # Called from extensions menu if this option is active
	session.open(SatScanLcn)

def SatScanLcnStart(menuid, **kwargs): # Menu position of plugin setup screen
	if menuid == "scan":
		return [(_("SatScanLcn"), SatScanLcnMain, "SatScanLcn_Setup", 11, True)]
	return []

def SatScanLcnMain(session, close=None, **kwargs): # calls setup screen
	session.openWithCallback(boundFunction(closeCallback, close), SatScanLcn_Setup)

def closeCallback(close=None, answer=None): # Called on exiting setup screen. Should force a recursive close on a succsssful scan.
	if close and answer:
		close(True)

def TerrestrialScanStart(menuid, **kwargs):
	if menuid == "scan" and nimmanager.getEnabledNimListOfType("DVB-T"):
		return [(_("Terrestrial Scan"), TerrestrialScanMain, "TerrestrialScan_Setup", 76, True)]
	return []

def TerrestrialScanMain(session, close=None, **kwargs):
	session.openWithCallback(boundFunction(closeCallback, close), TerrestrialScan_Setup)

def hasMultistream():
	return [nim for nim in nimmanager.nim_slots if nim.isCompatible("DVB-S") and nim.isMultistream()]

def MisPlsLcnScanStart(menuid, **kwargs):
	if menuid == "scan":
		return [(_("MIS/PLS LCN Scan"), MisPlsLcnScanMain, "MisPlsLcnScanScreen", 75, True)]
	return []

def MisPlsLcnScanMain(session, close=None, **kwargs):
	session.openWithCallback(boundFunction(closeCallback, close), MisPlsLcnScan_Setup)

def Plugins(**kwargs):
	plist = []
	if nimmanager.hasNimType("DVB-S"):
		plist.append( PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_MENU, needsRestart = False, fnc=SatScanLcnStart) )
		if config.plugins.satscanlcn.extensions.getValue():
			plist.append(PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=startdownload, needsRestart=True))
	else:
		print("[SatScanLcn] No DVB-S tuner available so don't load")
	if hasMultistream():
		plist.append(PluginDescriptor(name=_("MIS/PLS LCN Scan"), description="For scanning multiple input stream tv", where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=MisPlsLcnScanStart))
	else:
		print("[MisPlsLcnScan] No MIS/PLS capable tuner available so don't load")
	if nimmanager.hasNimType("DVB-T"):
		plist.append(PluginDescriptor(name=_("Terrestrial Scan"), description="For scanning terrestrial tv", where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=TerrestrialScanStart))
	else:
		print("[TerrestrialScan] No DVB-T tuner available so don't load")
	return plist
