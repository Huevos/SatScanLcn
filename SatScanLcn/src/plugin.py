# for localized messages
from . import _

description = _("Scans for services and creates a bouquet")

from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection, ConfigNumber, NoSave, ConfigClock, ConfigEnableDisable, ConfigSubDict
from Components.NimManager import nimmanager
from Plugins.Plugin import PluginDescriptor
from Tools.BoundFunction import boundFunction

from .satscanlcn import Scheduleautostart, SatScanLcn, SatScanLcn_Setup
from .providers import PROVIDERS

config.plugins.satscanlcn = ConfigSubsection()
config.plugins.satscanlcn.provider = ConfigSelection(default = "Orange_TV_16E", choices = [(x, PROVIDERS[x]["name"]) for x in sorted(PROVIDERS.keys())])
config.plugins.satscanlcn.extensions = ConfigYesNo(default = False)

# start: satscanlcn.schedule
config.plugins.satscanlcn.schedule = ConfigYesNo(default = False)
config.plugins.satscanlcn.scheduletime = ConfigClock(default = 0) # 1:00
config.plugins.satscanlcn.retry = ConfigNumber(default = 30)
config.plugins.satscanlcn.retrycount = NoSave(ConfigNumber(default = 0))
config.plugins.satscanlcn.nextscheduletime = ConfigNumber(default = 0)
config.plugins.satscanlcn.schedulewakefromdeep = ConfigYesNo(default = True)
config.plugins.satscanlcn.scheduleshutdown = ConfigYesNo(default = True)
config.plugins.satscanlcn.dayscreen = ConfigSelection(choices = [("1", _("Press OK"))], default = "1")
config.plugins.satscanlcn.days = ConfigSubDict()
for i in range(7):
	config.plugins.satscanlcn.days[i] = ConfigEnableDisable(default = True)
# end: satscanlcn.schedule

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

def SatScanLcnWakeupTime(): # Called on shutdown (going into deep standby) to tell the box when to wake from deep
	print("[SatScanLcn] next wake up due %d" % (config.plugins.satscanlcn.schedule.value and config.plugins.satscanlcn.schedulewakefromdeep.value and config.plugins.satscanlcn.nextscheduletime.value > 0 and config.plugins.satscanlcn.nextscheduletime.value or -1))
	return config.plugins.satscanlcn.schedule.value and config.plugins.satscanlcn.schedulewakefromdeep.value and config.plugins.satscanlcn.nextscheduletime.value > 0 and config.plugins.satscanlcn.nextscheduletime.value or -1

def Plugins(**kwargs):
	plist = []
	if nimmanager.hasNimType("DVB-S"):
		plist.append( PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_MENU, needsRestart = False, fnc=SatScanLcnStart) )
		plist.append(PluginDescriptor(name="SatScanLcnScheduler", where=[ PluginDescriptor.WHERE_AUTOSTART, PluginDescriptor.WHERE_SESSIONSTART ], fnc=Scheduleautostart, wakeupfnc=SatScanLcnWakeupTime, needsRestart=True))
		if config.plugins.satscanlcn.extensions.getValue():
			plist.append(PluginDescriptor(name=_("SatScanLcn"), description=description, where = PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=startdownload, needsRestart=True))
	return plist
