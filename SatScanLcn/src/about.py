from . import _
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.ScrollLabel import ScrollLabel

from Screens.Screen import Screen


class SatScanLcn_About(Screen):
	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Grab LCN bouquets from the DVB stream."))

		self.skinName = ["SatScanLcn_About", "Setup"]

		self["actions"] = ActionMap(["WizardActions", "ColorActions"],
		{
			"back": self.close,
			"red": self.close,
			"up": self.pageUp,
			"down": self.pageDown,
			"left": self.pageUp,
			"right": self.pageDown,
		}, -2)

		self["key_red"] = StaticText(_("Close"))

		from .version import PLUGIN_VERSION

		credits = [
			"SatScanLcn %s (c) 2021 \n" % PLUGIN_VERSION,
			"- http://github.com/Huevos\n",
			"- http://github.com/OpenViX\n",
			"- http://github.com/oe-alliance\n",
			"- http://www.world-of-satellite.com\n\n",
			_("Application credits:\n"),
			"- Huevos (main developer)\n\n",
			_("Sources credits (dvbreader):\n"),
			"- Sandro Cavazzoni aka skaman (main developer)\n",
			"- Andrew Blackburn aka AndyBlac (main developer)\n",
			"- Peter de Jonge aka PeterJ (developer)\n",
			"- Huevos (developer)\n\n",
			_("SatScanLCN grabs one simple bouquet of the selected provider and adds it to the top of the channel list. The bouquet can be moved using enigma's built in controls and will stay put on a rescan. To remove any bouquet created by this tool use enigma's built in controls.") + '\n\n',
			_("SatScanLCN is not meant to deprecate, replace, substitute, supersede or usurp any current bouquet creation tool.") + '\n\n',
			_("SatScanLCN expands on the JoyneScan plugin and uses the same dvbreader as ABM, but unlike ABM it is able to scan the Service Descriptor Table of multiple transponders based on the content of the Network Identification Table on the home transponder. This means providers such as Joyne (now defunct) or Orange TV on 16E that don't contain complete SDT data on the home transponder can still be successfully scanned.") + '\n\n',
			_("The bouquet is ordered exactly according to the Logical Channel Number data carried on the DVB stream. No cleanups, swaps or other manipulations are carried out. And no customisation of the produced bouquets is possible. If that is what is required please use ABM.") + '\n\n',
			_("Only one instance of each channel appears in the bouquet. If any channel is found to have multiple LCNs the lowest LCN numerically will be selected.") + '\n\n',
			_("To grab multiple bouquets just run the application multiple times.") + '\n\n',
		]

		self["config"] = ScrollLabel(''.join(credits))

	def pageUp(self):
		self["config"].pageUp()

	def pageDown(self):
		self["config"].pageDown()
