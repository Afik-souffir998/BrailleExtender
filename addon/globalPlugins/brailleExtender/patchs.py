# coding: utf-8
# patchs.py
# Part of BrailleExtender addon for NVDA
# Copyright 2016-2019 André-Abush CLAUSE, released under GPL.
# This file modify some functions from core.

from __future__ import unicode_literals
import os
import re
import sys
isPy3 = True if sys.version_info >= (3, 0) else False
import time
import unicodedata

import api
import appModuleHandler
import braille
import brailleInput
import brailleTables
import controlTypes
import config
from . import configBE
import globalCommands
import inputCore
import keyboardHandler
import louis
if isPy3: import louisHelper
import queueHandler
import sayAllHandler
import scriptHandler
import speech
import textInfos
import treeInterceptorHandler
import watchdog
from logHandler import log
import addonHandler
addonHandler.initTranslation()
from . import dictionaries
from . import huc
from .utils import getCurrentChar, getTether, getTextInBraille
instanceGP = None
chr_ = chr if isPy3 else unichr
HUCDotPattern = "12345678-78-12345678"
HUCUnicodePattern = huc.cellDescriptionsToUnicodeBraille(HUCDotPattern)
SELECTION_SHAPE = lambda: braille.SELECTION_SHAPE
errorTable = False
origFunc = {
	"script_braille_routeTo": globalCommands.GlobalCommands.script_braille_routeTo,
	"update": braille.Region.update,
	"_createTablesString": louis._createTablesString
}

def sayCurrentLine():
	global instanceGP
	if not instanceGP.autoScrollRunning:
		if getTether() == braille.handler.TETHER_REVIEW:
			if config.conf["brailleExtender"]["speakScroll"] in [configBE.CHOICE_focusAndReview, configBE.CHOICE_review]:
				scriptHandler.executeScript(globalCommands.commands.script_review_currentLine, None)
			return
		elif config.conf["brailleExtender"]["speakScroll"] in [configBE.CHOICE_focusAndReview, configBE.CHOICE_focus]:
			obj = api.getFocusObject()
			treeInterceptor = obj.treeInterceptor
			if isinstance(treeInterceptor, treeInterceptorHandler.DocumentTreeInterceptor) and not treeInterceptor.passThrough: obj = treeInterceptor
			try: info = obj.makeTextInfo(textInfos.POSITION_CARET)
			except (NotImplementedError, RuntimeError):
				info = obj.makeTextInfo(textInfos.POSITION_FIRST)
			info.expand(textInfos.UNIT_LINE)
			speech.speakTextInfo(info, unit=textInfos.UNIT_LINE, reason=controlTypes.REASON_CARET)

def getCurrentBrailleTables(input_=False):
	if input_:
		if instanceGP and instanceGP.BRFMode and not errorTable:
			tables = [
				os.path.join(configBE.baseDir, "res", "brf.ctb").encode("UTF-8"),
				os.path.join(brailleTables.TABLES_DIR, "braille-patterns.cti")
			]
		else:
			tables = []
			if brailleInput.handler._table.fileName == config.conf["braille"]["translationTable"]: tables += dictionaries.dictTables
			tables += [
				os.path.join(brailleTables.TABLES_DIR, brailleInput.handler._table.fileName),
				os.path.join(brailleTables.TABLES_DIR, "braille-patterns.cti")
			]
	else:
		if errorTable:
			if instanceGP and instanceGP.BRFMode: instanceGP.BRFMode = False
			tables = [
				os.path.join(brailleTables.TABLES_DIR, config.conf["braille"]["translationTable"]),
				os.path.join(brailleTables.TABLES_DIR, "braille-patterns.cti")
			]
		elif instanceGP and instanceGP.BRFMode:
			tables = [
				os.path.join(configBE.baseDir, "res", "brf.ctb").encode("UTF-8"),
				os.path.join(brailleTables.TABLES_DIR, "braille-patterns.cti")
			]
		else:
			tables = []
			app = appModuleHandler.getAppModuleForNVDAObject(api.getNavigatorObject())
			if app and app.appName != "nvda":
				tables += dictionaries.dictTables
			tables += [
				os.path.join(brailleTables.TABLES_DIR, config.conf["braille"]["translationTable"]),
				os.path.join(brailleTables.TABLES_DIR, "braille-patterns.cti")
			]
	return tables

# globalCommands.GlobalCommands.script_braille_routeTo()
def script_braille_routeTo(self, gesture):
	obj = obj = api.getNavigatorObject()
	if (config.conf["brailleExtender"]['routingReviewModeWithCursorKeys'] and
			obj.hasFocus and
			braille.handler._cursorPos and
			(obj.role == controlTypes.ROLE_TERMINAL or
			 (obj.role == controlTypes.ROLE_EDITABLETEXT and
			 getTether() == braille.handler.TETHER_REVIEW))):
		speechMode = speech.speechMode
		speech.speechMode = 0
		nb = braille.handler._cursorPos-gesture.routingIndex
		i = 0
		key = "leftarrow" if nb > 0 else "rightarrow"
		while i < abs(nb):
			keyboardHandler.KeyboardInputGesture.fromName(key).send()
			i += 1
		speech.speechMode = speechMode
		speech.speakSpelling(getCurrentChar())
		return
	braille.handler.routeTo(gesture.routingIndex)
	if scriptHandler.getLastScriptRepeatCount() == 0 and config.conf["brailleExtender"]['speakRoutingTo']:
		ch = getCurrentChar()
		if ch: speech.speakSpelling(ch)

# braille.Region.update()
def update(self):
	"""Update this region.
	Subclasses should extend this to update L{rawText}, L{cursorPos}, L{selectionStart} and L{selectionEnd} if necessary.
	The base class method handles translation of L{rawText} into braille, placing the result in L{brailleCells}.
	Typeform information from L{rawTextTypeforms} is used, if any.
	L{rawToBraillePos} and L{brailleToRawPos} are updated according to the translation.
	L{brailleCursorPos}, L{brailleSelectionStart} and L{brailleSelectionEnd} are similarly updated based on L{cursorPos}, L{selectionStart} and L{selectionEnd}, respectively.
	@postcondition: L{brailleCells}, L{brailleCursorPos}, L{brailleSelectionStart} and L{brailleSelectionEnd} are updated and ready for rendering.
	"""
	try:
		mode = louis.dotsIO
		if config.conf["braille"]["expandAtCursor"] and self.cursorPos is not None: mode |= louis.compbrlAtCursor
		if isPy3:
			self.brailleCells, self.brailleToRawPos, self.rawToBraillePos, self.brailleCursorPos = louisHelper.translate(
				getCurrentBrailleTables(),
				self.rawText,
				typeform=self.rawTextTypeforms,
				mode=mode,
				cursorPos=self.cursorPos
			)
		else:
			text = unicode(self.rawText).replace('\0', '')
			self.brailleCells, self.brailleToRawPos, self.rawToBraillePos, brailleCursorPos = louis.translate(getCurrentBrailleTables(),
				text,
				# liblouis mutates typeform if it is a list.
				typeform=tuple(
					self.rawTextTypeforms) if isinstance(
					self.rawTextTypeforms,
					list) else self.rawTextTypeforms,
				mode=mode,
				cursorPos=self.cursorPos or 0
			)
	except BaseException as e:
		global errorTable
		if not errorTable:
			log.error("Unable to translate with tables: %s\nDetails: %s" % (getCurrentBrailleTables(), e))
			errorTable = True
			if instanceGP.BRFMode: instanceGP.BRFMode = False
			instanceGP.errorMessage(_("An unexpected error was produced while using several braille tables. Using default settings to avoid other errors. More information in NVDA log. Thanks to report it."))
		return
	if config.conf["brailleExtender"]["undefinedCharReprType"] in [configBE.CHOICE_liblouis, configBE.CHOICE_HUC8, configBE.CHOICE_HUC6]: HUCProcess(self)
	if not isPy3:
		# liblouis gives us back a character string of cells, so convert it to a list of ints.
		# For some reason, the highest bit is set, so only grab the lower 8
		# bits.
		self.brailleCells = [ord(cell) & 255 for cell in self.brailleCells]
		# #2466: HACK: liblouis incorrectly truncates trailing spaces from its output in some cases.
		# Detect this and add the spaces to the end of the output.
		if self.rawText and self.rawText[-1] == " ":
			# rawToBraillePos isn't truncated, even though brailleCells is.
			# Use this to figure out how long brailleCells should be and thus
			# how many spaces to add.
			correctCellsLen = self.rawToBraillePos[-1] + 1
			currentCellsLen = len(self.brailleCells)
			if correctCellsLen > currentCellsLen:
				self.brailleCells.extend(
					(0,) * (correctCellsLen - currentCellsLen))
		if self.cursorPos is not None:
			# HACK: The cursorPos returned by liblouis is notoriously buggy (#2947 among other issues).
			# rawToBraillePos is usually accurate.
			try:
				brailleCursorPos = self.rawToBraillePos[self.cursorPos]
			except IndexError:
				pass
		else:
			brailleCursorPos = None
		self.brailleCursorPos = brailleCursorPos
	if self.selectionStart is not None and self.selectionEnd is not None:
		try:
			# Mark the selection.
			self.brailleSelectionStart = self.rawToBraillePos[self.selectionStart]
			if self.selectionEnd >= len(self.rawText):
				self.brailleSelectionEnd = len(self.brailleCells)
			else:
				self.brailleSelectionEnd = self.rawToBraillePos[self.selectionEnd]
			fn = range if isPy3 else xrange
			for pos in fn(self.brailleSelectionStart, self.brailleSelectionEnd):
				self.brailleCells[pos] |= SELECTION_SHAPE()
		except IndexError: pass
	else:
		if instanceGP and instanceGP.hideDots78:
			self.brailleCells = [(cell & 63) for cell in self.brailleCells]

def setUndefinedChar(t=None):
	if not t or t > CHOICE_HUC6 or t < 0: t = config.conf["brailleExtender"]["undefinedCharReprType"]
	if t == 0: return
	c = ["default", "12345678", "123456", '0', config.conf["brailleExtender"]["undefinedCharRepr"], "questionMark", "sign"] + [HUCDotPattern]*3
	v = c[t]
	if v in ["questionMark", "sign"]:
		if v == "questionMark": s = '?'
		else: s = config.conf["brailleExtender"]["undefinedCharRepr"]
		v = huc.unicodeBrailleToDescription(getTextInBraille(s, getCurrentBrailleTables()))
	louis.compileString(getCurrentBrailleTables(), bytes("undefined %s" % v, "ASCII"))

def getDescChar(c):
	n = ''
	try: n = "'%s'" % unicodedata.name(c)
	except ValueError: n = r"'\x%.4x'" % ord(c)
	return n

def getHexLiblouisStyle(s):
	if config.conf["brailleExtender"]["showNameUndefinedChar"]:
		s = getTextInBraille(''.join([getDescChar(c) for c in s]))
	else: s = getTextInBraille(''.join([r"'\x%.4x'" % ord(c) for c in s]))
	return s

def HUCProcess(self):
	unicodeBrailleRepr = ''.join([chr_(10240+cell) for cell in self.brailleCells])
	allBraillePos = [m.start() for m in re.finditer(HUCUnicodePattern, unicodeBrailleRepr)]
	allBraillePosDelimiters = [(pos, pos+3) for pos in allBraillePos]
	if not allBraillePos: return
	if config.conf["brailleExtender"]["undefinedCharReprType"] == configBE.CHOICE_liblouis:
		replacements = {braillePos: getHexLiblouisStyle(self.rawText[self.brailleToRawPos[braillePos]]) for braillePos in allBraillePos}
	else:
		HUC6 = True if config.conf["brailleExtender"]["undefinedCharReprType"] == configBE.CHOICE_HUC6 else False
		replacements = {braillePos: huc.convert(self.rawText[self.brailleToRawPos[braillePos]], HUC6=HUC6) for braillePos in allBraillePos}
	newBrailleCells = []
	newBrailleToRawPos = []
	newRawToBraillePos = []
	lenBrailleToRawPos = len(self.brailleToRawPos)
	alreadyDone = []
	i = 0
	for iBrailleCells, brailleCells in enumerate(self.brailleCells):
		brailleToRawPos = self.brailleToRawPos[iBrailleCells]
		if iBrailleCells in replacements and not replacements[iBrailleCells].startswith(HUCUnicodePattern[0]):
			toAdd = [ord(c)-10240 for c in replacements[iBrailleCells]]
			newBrailleCells += toAdd
			newBrailleToRawPos += [i] * len(toAdd)
			alreadyDone += list(range(iBrailleCells, iBrailleCells+3))
			i += 1
		else:
			if iBrailleCells in alreadyDone: continue
			newBrailleCells.append(self.brailleCells[iBrailleCells])
			newBrailleToRawPos += [i]
			if (iBrailleCells + 1) < lenBrailleToRawPos and self.brailleToRawPos[iBrailleCells+1] != brailleToRawPos:
				i += 1
	pos = -42
	for i, brailleToRawPos in enumerate(newBrailleToRawPos):
		if brailleToRawPos != pos:
			pos = brailleToRawPos
			newRawToBraillePos.append(i)
	self.brailleCells = newBrailleCells
	self.brailleToRawPos = newBrailleToRawPos
	self.rawToBraillePos = newRawToBraillePos
	if self.cursorPos: self.brailleCursorPos = self.rawToBraillePos[self.cursorPos]

#: braille.TextInfoRegion.nextLine()
def nextLine(self):
	try:
		dest = self._readingInfo.copy()
		moved = dest.move(self._getReadingUnit(), 1)
		if not moved:
			if self.allowPageTurns and isinstance(dest.obj, textInfos.DocumentWithPageTurns):
				try: dest.obj.turnPage()
				except RuntimeError: pass
				else: dest = dest.obj.makeTextInfo(textInfos.POSITION_FIRST)
			else: return
		dest.collapse()
		self._setCursor(dest)
		queueHandler.queueFunction(queueHandler.eventQueue, speech.cancelSpeech)
		queueHandler.queueFunction(queueHandler.eventQueue, sayCurrentLine)
	except BaseException: pass

#: braille.TextInfoRegion.previousLine()
def previousLine(self, start=False):
	try:
		dest = self._readingInfo.copy()
		dest.collapse()
		if start: unit = self._getReadingUnit()
		else: unit = textInfos.UNIT_CHARACTER
		moved = dest.move(unit, -1)
		if not moved:
			if self.allowPageTurns and isinstance(dest.obj, textInfos.DocumentWithPageTurns):
				try: dest.obj.turnPage(previous=True)
				except RuntimeError: pass
				else:
					dest = dest.obj.makeTextInfo(textInfos.POSITION_LAST)
					dest.expand(unit)
			else: return
		dest.collapse()
		self._setCursor(dest)
		queueHandler.queueFunction(queueHandler.eventQueue, speech.cancelSpeech)
		queueHandler.queueFunction(queueHandler.eventQueue, sayCurrentLine)
	except BaseException: pass

#: inputCore.InputManager.executeGesture
def executeGesture(self, gesture):
		"""Perform the action associated with a gesture.
		@param gesture: The gesture to execute.
		@type gesture: L{InputGesture}
		@raise NoInputGestureAction: If there is no action to perform.
		"""
		if watchdog.isAttemptingRecovery:
			# The core is dead, so don't try to perform an action.
			# This lets gestures pass through unhindered where possible,
			# as well as stopping a flood of actions when the core revives.
			raise NoInputGestureAction

		script = gesture.script
		if "brailleDisplayDrivers" in str(type(gesture)):
			if instanceGP.brailleKeyboardLocked and ((hasattr(script, "__func__") and script.__func__.__name__ != "script_toggleLockBrailleKeyboard") or not hasattr(script, "__func__")): return
			if not config.conf["brailleExtender"]['stopSpeechUnknown'] and gesture.script == None: stopSpeech = False
			elif hasattr(script, "__func__") and (script.__func__.__name__ in [
			"script_braille_dots", "script_braille_enter",
			"script_volumePlus", "script_volumeMinus", "script_toggleVolume",
			"script_hourDate",
			"script_ctrl", "script_alt", "script_nvda", "script_win",
			"script_ctrlAlt", "script_ctrlAltWin", "script_ctrlAltWinShift", "script_ctrlAltShift","script_ctrlWin","script_ctrlWinShift","script_ctrlShift","script_altWin","script_altWinShift","script_altShift","script_winShift"]
			or (
				not config.conf["brailleExtender"]['stopSpeechScroll'] and
			script.__func__.__name__ in ["script_braille_scrollBack","script_braille_scrollForward"])):
				stopSpeech = False
			else: stopSpeech = True
		else: stopSpeech = True

		focus = api.getFocusObject()
		if focus.sleepMode is focus.SLEEP_FULL or (focus.sleepMode and not getattr(script, 'allowInSleepMode', False)):
			raise NoInputGestureAction

		wasInSayAll=False
		if gesture.isModifier:
			if not self.lastModifierWasInSayAll:
				wasInSayAll=self.lastModifierWasInSayAll=sayAllHandler.isRunning()
		elif self.lastModifierWasInSayAll:
			wasInSayAll=True
			self.lastModifierWasInSayAll=False
		else:
			wasInSayAll=sayAllHandler.isRunning()
		if wasInSayAll:
			gesture.wasInSayAll=True

		speechEffect = gesture.speechEffectWhenExecuted
		if not stopSpeech: pass
		elif speechEffect == gesture.SPEECHEFFECT_CANCEL:
			queueHandler.queueFunction(queueHandler.eventQueue, speech.cancelSpeech)
		elif speechEffect in (gesture.SPEECHEFFECT_PAUSE, gesture.SPEECHEFFECT_RESUME):
			queueHandler.queueFunction(queueHandler.eventQueue, speech.pauseSpeech, speechEffect == gesture.SPEECHEFFECT_PAUSE)

		if log.isEnabledFor(log.IO) and not gesture.isModifier:
			self._lastInputTime = time.time()
			log.io("Input: %s" % gesture.identifiers[0])

		if self._captureFunc:
			try:
				if self._captureFunc(gesture) is False:
					return
			except BaseException:
				log.error("Error in capture function, disabling", exc_info=True)
				self._captureFunc = None

		if gesture.isModifier:
			raise NoInputGestureAction

		if config.conf["keyboard"]["speakCommandKeys"] and gesture.shouldReportAsCommand:
			queueHandler.queueFunction(queueHandler.eventQueue, speech.speakMessage, gesture.displayName)

		gesture.reportExtra()

		# #2953: if an intercepted command Script (script that sends a gesture) is queued
		# then queue all following gestures (that don't have a script) with a fake script so that they remain in order.
		if not script and scriptHandler._numIncompleteInterceptedCommandScripts:
			script=lambda gesture: gesture.send()


		if script:
			scriptHandler.queueScript(script, gesture)
			return

		raise NoInputGestureAction

#: brailleInput.BrailleInputHandler.emulateKey()
def emulateKey(self, key, withModifiers=True):
	"""Emulates a key using the keyboard emulation system.
	If emulation fails (e.g. because of an unknown key), a debug warning is logged
	and the system falls back to sending unicode characters.
	@param withModifiers: Whether this key emulation should include the modifiers that are held virtually.
		Note that this method does not take care of clearing L{self.currentModifiers}.
	@type withModifiers: bool
	"""
	if withModifiers:
		# The emulated key should be the last item in the identifier string.
		keys = list(self.currentModifiers)
		keys.append(key)
		gesture = "+".join(keys)
	else:
		gesture = key
	try:
		inputCore.manager.emulateGesture(keyboardHandler.KeyboardInputGesture.fromName(gesture))
		instanceGP.lastShortcutPerformed = gesture
	except BaseException:
		log.debugWarning("Unable to emulate %r, falling back to sending unicode characters"%gesture, exc_info=True)
		self.sendChars(key)

#: brailleInput.BrailleInputHandler._translate()
# reason for patching: possibility to lock modifiers, display modifiers in braille during input
def _translate(self, endWord):
	"""Translate buffered braille up to the cursor.
	Any text produced is sent to the system.
	@param endWord: C{True} if this is the end of a word, C{False} otherwise.
	@type endWord: bool
	@return: C{True} if translation produced text, C{False} if not.
	@rtype: bool
	"""
	assert not self.useContractedForCurrentFocus or endWord, "Must only translate contracted at end of word"
	if self.useContractedForCurrentFocus:
		# self.bufferText has been used by _reportContractedCell, so clear it.
		self.bufferText = u""
	oldTextLen = len(self.bufferText)
	pos = self.untranslatedStart + self.untranslatedCursorPos
	data = u"".join([chr_(cell | brailleInput.LOUIS_DOTS_IO_START) for cell in self.bufferBraille[:pos]])
	mode = louis.dotsIO | louis.noUndefinedDots
	if (not self.currentFocusIsTextObj or self.currentModifiers) and self._table.contracted:
		mode |=  louis.partialTrans
	self.bufferText = louis.backTranslate(getCurrentBrailleTables(True),
		data, mode=mode)[0]
	newText = self.bufferText[oldTextLen:]
	if newText:
		# New text was generated by the cells just entered.
		if self.useContractedForCurrentFocus or self.currentModifiers:
			# For contracted braille, an entire word is sent at once.
			# Don't speak characters as this is sent.
			# Also, suppress typed characters when emulating a command gesture.
			speech._suppressSpeakTypedCharacters(len(newText))
		else:
			self._uncontSentTime = time.time()
		self.untranslatedStart = pos
		self.untranslatedCursorPos = 0
		if self.currentModifiers or not self.currentFocusIsTextObj:
			if len(newText)>1:
				# Emulation of multiple characters at once is unsupported
				# Clear newText, so this function returns C{False} if not at end of word
				newText = u""
			else:
				self.emulateKey(newText)
		else:
			self.sendChars(newText)

	if endWord or (newText and (not self.currentFocusIsTextObj or self.currentModifiers)):
		# We only need to buffer one word.
		# Clear the previous word (anything before the cursor) from the buffer.
		del self.bufferBraille[:pos]
		self.bufferText = u""
		self.cellsWithText.clear()
		if not instanceGP.modifiersLocked:
			self.currentModifiers.clear()
			instanceGP.clearMessageFlash()
		self.untranslatedStart = 0
		self.untranslatedCursorPos = 0

	if newText or endWord:
		self._updateUntranslated()
		return True

	return False

#: louis._createTablesString()
def _createTablesString(tablesList):
	"""Creates a tables string for liblouis calls"""
	if sys.version_info.major == 2:
		if sys.platform == "win32":
			return b",".join([x.decode("UTF-8") if isinstance(x, str) else bytes(x) for x in tablesList])
		else:
			return b",".join([x.decode("UTF-8").encode("UTF-8") if isinstance(x, str) else bytes(x) for x in tablesList])
	else:
		if sys.platform == "win32":
			return b",".join([x.encode("mbcs") if isinstance(x, str) else bytes(x) for x in tablesList])
		else:
			return b",".join([x.encode("UTF-8") if isinstance(x, str) else bytes(x) for x in tablesList])

# applying patches
braille.Region.update = update
braille.TextInfoRegion.previousLine = previousLine
braille.TextInfoRegion.nextLine = nextLine
inputCore.InputManager.executeGesture = executeGesture
NoInputGestureAction = inputCore.NoInputGestureAction
brailleInput.BrailleInputHandler.emulateKey = emulateKey
brailleInput.BrailleInputHandler._translate = _translate
globalCommands.GlobalCommands.script_braille_routeTo = script_braille_routeTo
louis._createTablesString = _createTablesString
script_braille_routeTo.__doc__ = origFunc["script_braille_routeTo"].__doc__

