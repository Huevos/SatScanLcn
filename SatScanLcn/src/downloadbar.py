from enigma import getDesktop

def insertValues(xml, values):
	# The skin template is designed for a HD screen so the scaling factor is 720.
	# double negative to round up not round down
	return xml % tuple([-(x*getDesktop(0).size().height()/(-720)) for x in values])

def downloadBar():
	fontSize = 22
	downloadBarHeight = 36
	textBoxHeight = 30
	textBoxTopMargin = 4
	actionBoxLeftAlign = 7
	actionBoxWidth = 433
	statusBoxLeftAlign = 466
	statusBoxWidth = 433
	lockImageLeftAlign = 929
	lockImageTopMargin = 3
	lockImageWidth = 25
	lockImageHeight = 24
	tunerLetterLeftAlign = 955
	tunerLetterWidth = fontSize
	snrBoxLeftAlign = 980
	snrBoxWidth = 87 # up to 7 chars, e.g. "16.2 dB"
	progressTextBoxLeftAlign = 1080
	progressTextBoxWidth = 87
	progressPercentLeftAlign = 1187
	progressPercentBoxWidth = 73
	downloadBarXML = """
	<screen name="DownloadBar" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#54111112">
		<widget name="action" position="%d,%d" size="%d,%d" font="Regular;%d" transparent="1" foregroundColor="#ffffff"/>
		<widget name="status" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" transparent="1" foregroundColor="#ffffff"/>
		<widget source="Frontend" conditional="Frontend" render="Pixmap" pixmap="icons/lock_on.png" position="%d,%d" size="%d,%d" alphatest="on" scale="1">
			<convert type="FrontendInfo">LOCK</convert>
			<convert type="ConditionalShowHide"/>
		</widget>
		<widget source="Frontend" conditional="Frontend" render="Pixmap" pixmap="icons/lock_off.png" position="%d,%d" size="%d,%d" alphatest="on" scale="1">
			<convert type="FrontendInfo">LOCK</convert>
			<convert type="ConditionalShowHide">Invert</convert>
		</widget>
		<widget name="tuner_text" conditional="tuner_text" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" transparent="1" foregroundColor="#ffffff"/>
		<widget source="Frontend" conditional="Frontend" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="left" transparent="1" foregroundColor="#ffffff">
			<convert type="FrontendInfo">SNRdB</convert>
		</widget>
		<widget source="progress_text" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="right" transparent="1" foregroundColor="#ffffff">
			<convert type="ProgressToText">InText</convert>
		</widget>
		<widget source="progress_text" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="left" transparent="1" foregroundColor="#ffffff">
			<convert type="ProgressToText">InPercent</convert>
		</widget>
	</screen>"""
	downloadBarValues = [
		getDesktop(0).size().width(), downloadBarHeight, # downloadBarXML line 1, "screen" element
		actionBoxLeftAlign, textBoxTopMargin, actionBoxWidth, textBoxHeight, fontSize, # downloadBarXML line 2, "action" widget
		statusBoxLeftAlign, textBoxTopMargin, statusBoxWidth, textBoxHeight, fontSize, # downloadBarXML line 3, "status" widget
		lockImageLeftAlign, lockImageTopMargin, lockImageWidth, lockImageHeight, # downloadBarXML, "lock_on" widget
		lockImageLeftAlign, lockImageTopMargin, lockImageWidth, lockImageHeight, # downloadBarXML, "lock_off" widget
		tunerLetterLeftAlign, textBoxTopMargin, tunerLetterWidth, textBoxHeight, fontSize, # downloadBarXML, "tuner letter" widget
		snrBoxLeftAlign, textBoxTopMargin, snrBoxWidth, textBoxHeight, fontSize, # downloadBarXML, "SNR" widget
		progressTextBoxLeftAlign, textBoxTopMargin, progressTextBoxWidth, textBoxHeight, fontSize, # downloadBarXML, "progress text" widget
		progressPercentLeftAlign, textBoxTopMargin, progressPercentBoxWidth, textBoxHeight, fontSize, # downloadBarXML, "progress percent" widget
	]
	return insertValues(downloadBarXML, downloadBarValues)