import pyctags, json
import sublime_plugin
import sublime
import subprocess
import re
import os

class TagMonster:
	def __init__(self):
		self.tagLookup = {}
		self.names = []
		pass

	def load_tag_file(self):
		self.settings = sublime.load_settings("TagMonster.sublime-settings")
		tag_files = self.settings.get('tag_files')
		ignore_regex = re.compile(self.settings.get("ignore_tag_regex").encode('ascii', 'ignore'))

		self.names = []
		self.tagLookup = {}
		self.scopeWiseNames = {}

		for tags_item in tag_files:
			self.scopeWiseNames[tags_item['scope']] = []

			fileName = tags_item["file_path"]
			base_dir = os.path.dirname(os.path.abspath(fileName))
			tagFile = pyctags.ctags_file()

			tagFile.parse(fileName.encode('ascii', 'ignore'))

			for tag in tagFile.tags:
				if ignore_regex.match(tag.name):
					continue
					
				self.names.append(tag.name)

				# populate scopewise names for writing completion caches
				self.scopeWiseNames[tags_item['scope']].append(tag.name)

				self.tagLookup[tag.name] = {
					'file': os.path.join(base_dir, tag.file),
					'pattern': tag.pattern
				}

	def write_completion_dict(self):
		compCacheFolder = os.path.abspath("./completion_cache")

		if not os.path.isdir(compCacheFolder):
			os.path.mkdir(compCacheFolder)

		# Clear out the directory
		for compFile in os.listdir(compCacheFolder):
			fileName = os.path.join(compCacheFolder, compFile)
			if os.path.isfile(fileName):
				os.unlink(fileName)

		index = 0
		for scope, names in self.scopeWiseNames.iteritems():
			handle = open(os.path.join(compCacheFolder, "tagmonster_" + str(index) + ".sublime-completions"), 'w')
			completionDict = {
				'scope': scope,
				'completions': names
			}

			handle.write(json.dumps(completionDict, indent=4))
			index += 1

	def rebuild_tags(self):
		self.settings = sublime.load_settings("TagMonster.sublime-settings")
		rebuild_tags_command = (self.settings.get('rebuild_tags_command'))
		subprocess.check_call(rebuild_tags_command, shell = True)
		tagMonster.load_tag_file()
		tagMonster.write_completion_dict()

	def open_tag_in_file(self, tag, window):
		self.window = window

		# open the file
		tagView = self.window.open_file(tag['file'])
		print("opening ", tag['file'])

		# Show the pattern in the view
		self.find_in_view(tagView, tag['pattern'])

	def find_in_view(self, tagView, pattern):
		if tagView.is_loading():
			sublime.set_timeout(lambda: self.find_in_view(tagView, pattern), 100)
		else:
			# Convert from pattern that ctags provides into a nice format we can use
			regex = re.escape(pattern[2:len(pattern) - 2])
			print("Trying to find", regex)
			patternRegion = tagView.find(regex, 0)
			if patternRegion == None:
				print("Couldn't find the pattern region. the tags might be obsolete")
			else:
				tagView.show(patternRegion, True)

	def peek_at_tag(self, tag, window):
		self.window = window
		print("opening tag ", tag)

		matcher = re.compile(re.escape(tag['pattern'][2:len(tag['pattern']) - 2]))
		lines = open(tag['file']).read().split(os.linesep)

		for i in range(0, len(lines)):
			if matcher.match(lines[i]):
				break

		if i == len(lines) - 1:
			return

		self.settings = sublime.load_settings("TagMonster.sublime-settings")
		# context_size = self.settings.get("context_lines")
		context_size = 5;
		length = len(lines)

		context_before = context_size if (context_size) <= i - 1 else i
		context_after = context_size if (context_size < (length - 1 - i)) else (context_size < (length - 1 - i))

		# Rebuild the context
		context = os.linesep.join(lines[i - context_before:i + context_after])

		# Create a view for the panel
		panel = self.window.get_output_panel("tagmonster_peek")
		panel.set_read_only(False)
		edit = panel.begin_edit()
		panel.erase(edit, sublime.Region(0, panel.size()))
		panel.insert(edit, panel.size(), context)
		panel.set_read_only(True)
		self.window.run_command("show_panel", {"panel": "output.tagmonster_peek"})
		panel.end_edit(edit)

# Create a new instance and simply load the tags. don't rebuild
tagMonster = TagMonster()
tagMonster.load_tag_file()

class RebuildTagsCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		# Do an entire rebuild
		tagMonster.rebuild_tags()


class JumpToTagCommandBase(sublime_plugin.WindowCommand):
	def run(self):
		tagNames = tagMonster.names

		self.window.show_quick_panel(tagNames, self.on_tag_picked)

	def on_tag_picked(self, index):
		print("Tag picked", index)

		if index == -1:
			return
		
		name = tagMonster.names[index]

		# perform a lookup
		tag = tagMonster.tagLookup[name]

		self.open_tag(tag)


class JumpToTagCommand(JumpToTagCommandBase):
	def open_tag(self, tag):
		tagMonster.open_tag_in_file(tag, self.window)

class PeekAtTagCommand(JumpToTagCommandBase):
	def open_tag(self, tag):
		tagMonster.peek_at_tag(tag, self.window)

class CurrentWordCommandBase(sublime_plugin.TextCommand):
	def run(self, view):
		current_word = self.view.substr(self.view.word(self.view.sel()[0]))

		if tagMonster.tagLookup.has_key (current_word):
			self.open_tag(tagMonster.tagLookup[current_word])
		else:
			print("Cannot find tag", current_word)
			sublime.status_message("Cannot find tag '" + current_word + "'")

class JumpToCurrentWordCommand(CurrentWordCommandBase):
	def open_tag(self, tag):
		window = self.view.window()
		tagMonster.open_tag_in_file(tag, window)

class PeekAtCurrentWordCommand(CurrentWordCommandBase):
	def open_tag(self, tag):
		window = self.view.window()
		tagMonster.peek_at_tag(tag, window)