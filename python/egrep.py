# -*- coding: utf-8 -*-
###
# Copyright (c) 2009 by Elián Hanisch <lambdae2@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
###

###
# Search in Weechat buffers and logs (for Weechat 0.3.*)
#
#   Inspired by xt's grep.py
#   Originally I just wanted to add some fixes in grep.py, but then
#   I got carried away and rewrote everything, so new script.
#
#   Commands:
#   * /egrep
#     Search in logs or buffers, see /help egrep
#   * /logs:
#     Lists logs in ~/.weechat/logs, see /help logs
#
#   Settings:
#   * plugins.var.python.clear_buffer:
#     Clear the results buffer before each search. Valid values: on, off
#   * plugins.var.python.log_filter:
#     Coma separated list of patterns that egrep will use for exclude logs, e.g.
#     if you use '*server/*' any log in the 'server' folder will be excluded
#     when using the command '/egrep log'
#   * plugins.var.python.show_summary:
#     Shows summary for each log. Valid values: on, off
#
#
#   TODO:
#   * grepping should run in background for big logs
#
#
#   History:
#   2009-08-17
#   version 0.5.1: some refactoring, show_summary option added.
#
#   2009-08-13
#   version 0.5: rewritten from xt's grep.py
#   * fixed searching in non weechat logs, for cases like, if you're
#     switching from irssi and rename and copy your irssi logs to %h/logs
#   * fixed "timestamp rainbow" when you /grep in grep's buffer
#   * allow to search in other buffers other than current or in logs
#     of currently closed buffers with cmd 'buffer'
#   * allow to search in any log file in %h/logs with cmd 'log'
#   * added --count for return the number of matched lines
#   * added --matchcase for case sensible search
#   * added --hilight for color matches
#   * added --head and --tail options, and --number
#   * added command /logs for list files in %h/logs
#   * added config option for clear the buffer before a search
#   * added config option for filter logs we don't want to grep
#   * added the posibility to repeat last search with another regexp by writing
#     it in egrep's buffer
#   * changed spaces for tabs in the code, which is my preference
#
###

from __future__ import with_statement # This isn't required in Python 2.6
import os.path as path
import getopt

import weechat
from weechat import WEECHAT_RC_OK

SCRIPT_NAME    = "egrep"
SCRIPT_AUTHOR  = "Elián Hanisch <lambdae2@gmail.com>"
SCRIPT_VERSION = "0.5.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESC    = "Search in buffers and logs"
SCRIPT_COMMAND = "egrep"

script_nick    = '***'

### class definitions
class linesDict(dict):
	"""
	Class for handling matched lines in more than one buffer.
	linesDict[buffer_name] = matched_lines_list
	"""
	def __setitem__(self, key, value):
		# probably I'm being too carefull.
		assert isinstance(value, list)
		assert isinstance(key, str)
		dict.__setitem__(self, key, value)

	def __len__(self):
		"""Return the sum of total lines stored."""
		if dict.__len__(self):
			return sum(map(len, self.itervalues()))
		else:
			return 0

	def __str__(self):
		"""Returns buffer count or buffer name if there's just one stored."""
		n = len(self.keys())
		if n == 1:
			return self.keys()[0]
		elif n > 1:
			return '%s logs' %n
		else:
			return ''

class ValidValuesDict(dict):
	"""
	Dict that returns the default value defined by 'defaultKey' key if __getitem__ raises
	KeyError. 'defaultKey' must be in the supplied dict.
	"""
	def _error_msg(self, key):
		error("'%s' is an invalid option value, allowed: %s. Defaulting to '%s'" \
				%(key, ', '.join(map(repr, self.keys())), self.default))

	def __init__(self, dict, defaultKey):
		self.update(dict)
		assert defaultKey in self
		self.default = defaultKey

	def __getitem__(self, key):
		try:
			return dict.__getitem__(self, key)
		except KeyError:
			# user set a bad value
			self._error_msg(key)
			return dict.__getitem__(self, self.default)

### config
settings = (
		('clear_buffer', 'off'), # Should clear the buffer before every search
		('log_filter', ''), # filter for exclude log files
		('show_summary', 'on')) # Show summary line after the search

# I can't find for the love of me how to easily add a boolean config option in plugins.var.python
# config_set_plugin sets a string option and any string is valid, will do value validation here.
boolDict = ValidValuesDict({'on':True, 'off':False}, 'off')
def get_config_boolean(config):
	"""Gets our config value, returns a sane default if value is wrong."""
	return boolDict[weechat.config_get_plugin(config)]

def get_config_log_filter():
	filter = weechat.config_get_plugin('log_filter')
	if filter:
		return filter.split(',')
	else:
		return []

def get_home():
	home = weechat.config_string(weechat.config_get('logger.file.path'))
	return home.replace('%h', weechat.info_get('weechat_dir', ''))

### messages
def debug(s, prefix='debug'):
	"""Debug msg"""
	weechat.prnt('', '%s: %s'  %(prefix,s))

def error(s, prefix=SCRIPT_NAME, buffer=''):
	"""Error msg"""
	weechat.prnt(buffer, '%s%s: %s' %(weechat.prefix('error'), prefix, s))

def say(s, prefix=SCRIPT_NAME, buffer=''):
	"""normal msg"""
	weechat.prnt(buffer, '%s: %s' %(prefix, s))

### formatting
def color_nick(nick):
	"""Returns coloured nick, with coloured mode if any."""
	# XXX should check if nick has a prefix and subfix string?
	if not nick: return ''
	# nick mode
	modes = '@!+%' # XXX I hope I got them right
	if nick[0] in modes:
		mode, nick = nick[0], nick[1:]
		mode_color = weechat.config_string(weechat.config_get('weechat.color.nicklist_prefix%d' \
			%(modes.find(mode) + 1)))
		mode_color = weechat.color(mode_color)
	else:
		mode = ''
		mode_color = ''
	color_nicks_number = weechat.config_integer(weechat.config_get('weechat.look.color_nicks_number'))
	idx = (sum(map(ord, nick))%color_nicks_number) + 1
	color = weechat.config_string(weechat.config_get('weechat.color.chat_nick_color%02d' %idx))
	nick_color = weechat.color(color)
	return '%s%s%s%s' %(mode_color, mode, nick_color, nick)

def color_hilight(s, list):
	"""Returns 's' with strings in 'list' coloured."""
	# remove duplicates in match list if any
	d = {}
	for m in list:
		d[m] = 1
	list = d.keys()
	# apply hilight
	for m in list:
		s = s.replace(m, '%s%s%s' %(colors['hilight'], m, colors['reset']))
	return s

def format_line(s, hilight):
	"""Returns the log line 's' ready for printing in buffer."""
	date, nick, msg = split_line(s)
	# we don't want colors if there's match highlighting
	if hilight:
		# fix color reset when there's highlighting from date to prefix
		if colors['hilight'] in date and not colors['reset'] in date:
			nick = colors['hilight'] + nick
		return '%s\t%s %s' %(date, nick, msg)
	else:
		nick = color_nick(nick)
		return '%s%s\t%s%s %s' %(colors['date'], date, nick, colors['reset'], msg)

def split_line(s):
	"""Split 's' in (date, nick, msg), if 's' isn't in weechat's formats returns ('', '', s)."""
	global weechat_format
	if weechat_format and s.count('\t') >= 2:
		return s.split('\t', 2) # date, nick, message
	else:
		# looks like log isn't in weechat's format
		weechat_format = False # incoming lines won't be formatted if they have 2 tabs
		return '', '', s.replace('\t', ' ')

# for /logs cmd
sizeDict = {0:'b', 1:'KiB', 2:'MiB', 3:'GiB', 4:'TiB'}
def human_readable_size(size):
	power = 0
	while size > 1024:
		power += 1
		size /= 1024.0
	return '%.2f%s' %(size, sizeDict.get(power, ''))

### log files and buffers
cache_dir = {} # for avoid walking the dir tree more than once per command
def dir_list(dir, filter_list=(), filter_excludes=True):
	"""Returns a list of files in 'dir' and its subdirs."""
	global cache_dir
	import fnmatch
	#debug('dir_list: listing in %s' %dir)
	if dir in cache_dir:
		#debug('dir_list: using dir cache.')
		return cache_dir[dir]

	def append_files(arg, dir, fnames):
		arg.extend(map(lambda s:path.join(dir, s), fnames))

	def filter(file):
		if path.isdir(file):
			return True
		elif filter_list:
			file = file[len(dir):] # pattern shouldn't match home dir
			for pattern in filter_list:
				if fnmatch.fnmatch(file, pattern):
					return filter_excludes
		return not filter_excludes

	file_list = []
	filter_list = filter_list or get_config_log_filter()
	#debug('filter: %s' %filter_list)
	path.walk(dir, append_files, file_list) # get a list of log files, including in subdirs
	file_list = [ file for file in file_list if not filter(file) ]
	cache_dir[dir] = file_list
	return file_list

def get_file_by_pattern(pattern, all=False):
	"""Returns the first log whose path matches 'pattern',
	if all is True returns all logs that matches."""
	global home_dir
	if not pattern: return []
	#debug('get_file_by_filename: searching for %s.' %pattern)
	file = path.join(home_dir, pattern)
	if not path.isfile(file):
		# lets see if there's a log matching pattern
		import fnmatch
		file = []
		file_list = dir_list(home_dir)
		n = len(home_dir)
		for log in file_list:
			basename = log[n:]
			if fnmatch.fnmatch(basename, pattern):
				file.append(log)
				if not all: break
	else:
		file = [file]
	#debug('get_file_by_filename: got %s.' %file)
	return file

def get_file_by_buffer(buffer):
	"""Given buffer pointer, finds log's path or returns None."""
	#debug('get_file_by_buffer: searching for %s' %buffer)
	file = None
	log_enabled = False
	infolist = weechat.infolist_get('logger_buffer', '', '')
	while weechat.infolist_next(infolist):
		pointer = weechat.infolist_pointer(infolist, 'buffer')
		if pointer == buffer:
			file = weechat.infolist_string(infolist, 'log_filename')
			log_enabled = weechat.infolist_integer(infolist, 'log_enabled')
			break
	weechat.infolist_free(infolist)
	#debug('get_file_by_buffer: log_enabled: %s got: %s' %(log_enabled, file))
	if not log_enabled:
		return None
	return file

def get_file_by_name(buffer_name):
	"""Given a buffer name, returns its log path or None. buffer_name should be in 'server.#channel'
	or '#channel' format."""
	#debug('get_file_by_name: searching for %s' %buffer_name)
	# get common mask options
	masks = [weechat.config_string(weechat.config_get('logger.mask.irc'))]
	masks.append(weechat.config_string(weechat.config_get('logger.file.mask')))
	# I can't see how to replace all the local vars in mask nicely, so I just replace $channel,
	# $server and other local vars, replace the unreplaced vars left with '*', and use it as
	# a mask for get the path with get_file_by_pattern
	for mask in masks:
		#debug('get_file_by_name: mask: %s' %mask)
		if '$name' in mask:
			mask = mask.replace('$name', buffer_name)
		elif '$channel' in mask or '$server' in mask or '$short_name' in mask:
			if '.' in buffer_name and \
					'#' not in buffer_name[:buffer_name.find('.')]: # the dot isn't part of the channel name
				#	 ^ I'm asuming channel starts with #, i'm lazy.
				server, channel = buffer_name.split('.', 1)
			else:
				server, channel = '', buffer_name
			mask = mask.replace('$short_name', channel)
			mask = mask.replace('$channel', channel)
			if server:
				mask = mask.replace('$server', server)
		# change the unreplaced vars by '*'
		if '$' in mask:
			chars = 'abcdefghijklmnopqrstuvwxyz_'
			masks = mask.split('$')
			masks = map(lambda s: s.lstrip(chars), masks)
			mask = '*'.join(masks)
			if not mask.startswith('*'):
				mask = '*' + mask
		#debug('get_file_by_name: using mask %s' %mask)
		file = get_file_by_pattern(mask)
		if file:
			return file
	return None

def get_buffer_by_name(buffer_name):
	"""Given a buffer name returns its buffer pointer or None."""
	#debug('get_buffer_by_name: searching for %s' %buffer_name)
	pointer = weechat.buffer_search('', buffer_name)
	if not pointer:
		infolist = weechat.infolist_get('buffer', '', '')
		while weechat.infolist_next(infolist) and not pointer:
			name = weechat.infolist_string(infolist, 'name')
			if buffer_name in name:
				#debug('get_buffer_by_name: found %s' %name)
				pointer = weechat.buffer_search('', name)
		weechat.infolist_free(infolist)
	#debug('get_buffer_by_name: got %s' %pointer)
	if pointer:
		return pointer
	return None

def get_all_buffers():
	"""Returns list with pointers of all open buffers."""
	buffers = []
	infolist = weechat.infolist_get('buffer', '', '')
	while weechat.infolist_next(infolist):
		buffers.append(weechat.infolist_pointer(infolist, 'pointer'))
	weechat.infolist_free(infolist)
	return buffers

### grep
def make_regexp(pattern, matchcase=False):
	"""Returns a compiled regexp."""
	try:
		import re
		if not matchcase:
			regexp = re.compile(pattern, re.IGNORECASE)
		else:
			regexp = re.compile(pattern)
	except Exception, e:
		raise Exception, 'Bad pattern, %s' %e
	return regexp

def check_string(s, regexp, hilight=False, exact=False):
	"""Checks 's' with a regexp and returns it if is a match."""
	if not regexp:
		return s
	elif exact:
		matchlist = regexp.findall(s)
		if matchlist:
			return ' '.join(matchlist)
	elif hilight:
		matchlist = regexp.findall(s)
		if matchlist:
			return color_hilight(s, matchlist)
	# no need for findall() here
	elif regexp.search(s):
		return s

def grep_file(file, head, tail, *args):
	"""Return a list of lines that match 'regexp' in 'file', if no regexp returns all lines."""
	lines = []
	with open(file, 'r') as file_object:
		if tail:
			# instead of searching in the whole file and later pick the last few lines, we read the
			# log, reverse it, search until count reached and reverse it again, that way is a lot
			# faster
			fd = file_object.readlines()
			fd.reverse()
		else:
			fd = file_object
		limit = head or tail
		for line in fd:
			line = check_string(line, *args)
			if line:
				lines.append(line)
				if limit and len(lines) >= limit: break
	if tail:
		lines.reverse()
	return lines

def grep_buffer(buffer, head, tail, *args):
	"""Return a list of lines that match 'regexp' in 'buffer', if no regexp returns all lines."""
	lines = []
	# Using /grep in grep's buffer can lead to some funny effects
	# We should take measures if that's the case
	grep_buffer = weechat.buffer_search('python', SCRIPT_NAME)
	grep_buffer = buffer == grep_buffer
	infolist = weechat.infolist_get('buffer_lines', buffer, '')
	if tail:
		# like with grep_file() if we need the last few matching lines, we move the cursor to
		# the end and search backwards
		infolist_next = weechat.infolist_prev
	else:
		infolist_next = weechat.infolist_next
	limit = head or tail
	while infolist_next(infolist):
		prefix = weechat.infolist_string(infolist, 'prefix')
		message = weechat.infolist_string(infolist, 'message')
		prefix = weechat.string_remove_color(prefix, '')
		message = weechat.string_remove_color(message, '')
		if grep_buffer:
			if script_nick == prefix: # ignore our lines
				continue
			date = prefix
			line = '%s\t%s' %(date, message.replace(' ', '\t', 1))
		else:
			date = weechat.infolist_time(infolist, 'date')
			line = '%s\t%s\t%s' %(date, prefix, message)
		line = check_string(line, *args)
		if line:
			lines.append(line)
			if limit and len(lines) >= limit:
				break
	weechat.infolist_free(infolist)
	if tail:
		lines.reverse()
	return lines

### this is our main grep function
def get_matching_lines(logs, *args):
	"""
	get_matching_lines(logs, head, tail, regexp, hilight, exact) => linesDict
	Given a list of log files or buffer pointers, returns a linesDict with the matching lines
	"""
	global home_dir
	matched_lines = linesDict()
	for log in logs:
		if log == '' or log.startswith('0x'):
			# is a buffer
			buffer_name = weechat.buffer_get_string(log, 'name')
			matched_lines[buffer_name] = grep_buffer(log, *args)
		else:
			# is a file
			log_name = log[len(home_dir):]
			matched_lines[log_name] = grep_file(log, *args)
	return matched_lines

### output buffer
make_title = lambda pattern, buffer, count: \
	"Search in '%s' matched %s lines, pattern: '%s'" \
		%(buffer, count, pattern)
def buffer_update(matched_lines, pattern, count, *args):
	"""Updates our buffer with new lines."""
	buffer = buffer_create()
	title = make_title(pattern, matched_lines, len(matched_lines))
	weechat.buffer_set(buffer, 'title', title)
	if matched_lines: # lines matched in at least one log
		for log, lines in matched_lines.iteritems():
			if not count:
				for line in lines:
					weechat.prnt(buffer, format_line(line, *args))
			info = make_title(pattern, log, len(lines))
			if get_config_boolean('show_summary'):
				print_info(info, buffer)
	else:
		print_info(title, buffer)
	weechat.buffer_set(buffer, 'display', '1')

def print_info(s, buffer=None, display=False):
	"""Prints 's' in script's buffer as 'script_nick'. For displaying search summaries."""
	if buffer is None:
		buffer = buffer_create()
	weechat.prnt(buffer, '%s%s\t%s%s' \
			%(colors['script_nick'],script_nick, colors['info'], s))
	if display:
		weechat.buffer_set(buffer, 'display', '1')

def buffer_create():
	"""Returns our buffer pointer, creates and cleans the buffer if needed."""
	buffer = weechat.buffer_search('python', SCRIPT_NAME)
	if not buffer:
		buffer = weechat.buffer_new(SCRIPT_NAME, 'buffer_input', '', 'buffer_close', '')
		weechat.buffer_set(buffer, 'time_for_each_line', '0')
		weechat.buffer_set(buffer, 'nicklist', '0')
		weechat.buffer_set(buffer, 'title', 'egrep output buffer')
		weechat.buffer_set(buffer, 'localvar_set_no_log', '1')
	else:
		if get_config_boolean('clear_buffer'):
			weechat.buffer_clear(buffer)
	return buffer

def buffer_input(data, buffer, input_data):
	"""Repeats last search with 'input_data' as regexp."""
	global last_search
	if last_search and input_data:
		logs, head, tail, regexp, hilight, exact, count, matchcase = last_search
		try:
			regexp = make_regexp(input_data, matchcase)
		except Exception, e:
			error(e, buffer=buffer)
			return WEECHAT_RC_OK
		# lets be sure that our pointers in 'logs' are still valid
		for log in logs:
			if log.startswith('0x') and not weechat.infolist_get('buffer', log, ''):
				# I don't want any crashes
				error("Got invalid pointer, did you close a buffer? use /egrep", buffer=buffer)
				return WEECHAT_RC_OK
		matched_lines = get_matching_lines(logs, head, tail, regexp, hilight, exact)
		buffer_update(matched_lines, input_data, count, hilight)
	elif not last_search:
		error("There isn't any previous search to repeat.", buffer=buffer)
	return WEECHAT_RC_OK

def buffer_close(*args):
	return WEECHAT_RC_OK

### commands
def cmd_init():
	global home_dir, weechat_format, cache_dir, last_search
	home_dir = get_home()
	weechat_format = True
	cache_dir = {}
	last_search = None

def cmd_grep(data, buffer, args):
	"""Search in buffers and logs."""
	global home_dir, last_search
	if not args:
		weechat.command('', '/help %s' %SCRIPT_COMMAND)
		return WEECHAT_RC_OK
	# set defaults
	log_name = buffer_name = ''
	head = tail = matchcase = count = all = exact = hilight = False
	number = None
	# parse
	try:
		opts, args = getopt.gnu_getopt(args.split(), 'cmHeahtin:', ['count', 'matchcase', 'hilight',
			'exact', 'all', 'head', 'tail', 'number='])
		#debug(opts, 'opts: '); debug(args, 'args: ')
		if len(args) >= 2:
			if args[0] == 'log':
				del args[0]
				log_name = args.pop(0)
			elif args[0] == 'buffer':
				del args[0]
				buffer_name = args.pop(0)
		pattern = ' '.join(args) # join pattern for keep spaces
		if not pattern:
			raise Exception, 'No pattern for grep the logs.'
		elif pattern in ('.', '.*', '.?', '.+'):
			pattern = '' # because I don't need to use a regexp if we're going to match all lines.
		for opt, val in opts:
			opt = opt.strip('-')
			if opt in ('c', 'count'):
				count = True
			if opt in ('m', 'matchcase'):
				matchcase = True
			if opt in ('H', 'hilight'):
				hilight = True
			if opt in ('e', 'exact'):
				exact = True
			if opt in ('a', 'all'):
				all = True
			if opt in ('h', 'head'):
				head = True
			if opt in ('t', 'tail'):
				tail = True
			if opt in ('n', 'number'):
				try:
					number = int(val)
					if number < 0:
						raise ValueError
				except ValueError:
					raise Exception, "argument for --number must be a integer positive number."
		# more checks
		if count:
			if hilight:
				hilight = False # why hilight if we're just going to count?
			if exact:
				exact = False # see hilight
		if head and tail: # it won't work
			raise Exception, "can't use --tail and --head simultaneously."
		if number is not None:
			if not head and not tail:
				raise Exception, "--number only works with --tail or --head."
			if number == 0:
				# waste of cpu cycles
				say("This humble script refuses to search and return zero lines.", buffer=buffer)
				return WEECHAT_RC_OK
			if head:
				head = number
			elif tail:
				tail = number
		else:
			if head:
				head = 10
			elif tail:
				tail = 10
		regexp = pattern and make_regexp(pattern, matchcase)
	except Exception, e:
		error('Argument error, %s' %e)
		return WEECHAT_RC_OK
	# lets start
	cmd_init()
	log_file = search_buffer = None
	if log_name:
		log_file = get_file_by_pattern(log_name, all)
		if not log_file:
			error("Couldn't find any log for %s. Try /logs" %log_name)
			return WEECHAT_RC_OK
	elif all:
		search_buffer = get_all_buffers()
	elif buffer_name:
		search_buffer = get_buffer_by_name(buffer_name)
		if search_buffer is None:
			# there's no buffer, try in the logs
			log_file = get_file_by_name(buffer_name)
			if not log_file:
				error("Logs or buffer for '%s' not found." %buffer_name)
				return WEECHAT_RC_OK
		else:
			search_buffer = [search_buffer]
	else:
		search_buffer = [buffer]
	# make the log list
	logs = []
	if log_file:
		logs = log_file
	else:
		for pointer in search_buffer:
			log = get_file_by_buffer(pointer)
			if log:
				logs.append(log)
			else:
				logs.append(pointer)
	# grepping
	#debug('Grepping in %s' %logs)
	try:
		matched_lines = get_matching_lines(logs, head, tail, regexp, hilight, exact)
		# save last search
		last_search = (logs, head, tail, regexp, hilight, exact, count, matchcase)
	except Exception, e:
		error(e)
		return WEECHAT_RC_OK
	# output
	buffer_update(matched_lines, pattern, count, hilight)
	return WEECHAT_RC_OK

def cmd_logs(data, buffer, args):
	"""List files in Weechat's log dir."""
	global home_dir
	from os import stat
	get_size = lambda x: stat(x).st_size
	sort_by_size = False
	filter = []
	try:
		opts, args = getopt.gnu_getopt(args.split(), 's', ['size'])
		if args:
			filter = args
		for opt, var in opts:
			opt = opt.strip('-')
			if opt in ('size', 's'):
				sort_by_size = True
	except Exception, e:
		error('Argument error, %s' %e)
		return WEECHAT_RC_OK
	# args look good
	cmd_init()
	# is there's a filter, filter_excludes should be False
	file_list = dir_list(home_dir, filter, filter_excludes=not filter)
	home_dir_len = len(home_dir)
	if sort_by_size:
		file_list.sort(key=get_size)
	else:
		file_list.sort()
	file_sizes = map(lambda x: human_readable_size(get_size(x)), file_list)
	if weechat.config_string(weechat.config_get('weechat.look.prefix_align')) == 'none' \
			and file_list:
		# lets do alignment for the file list
		L = file_sizes[:]
		L.sort(key=len)
		bigest = L[-1]
		column_len = len(bigest)
	else:
		column_len = ''
	buffer = buffer_create()
	file_list = zip(file_list, file_sizes)
	msg = 'Found %s logs.' %len(file_list)
	print_info(msg, buffer, display=True)
	for file, size in file_list:
		separator = column_len and ' '*(column_len - len(size))
		weechat.prnt(buffer, '%s%s\t%s' %(separator, size, file[home_dir_len:]))
	if file_list:
		print_info(msg, buffer)
	return WEECHAT_RC_OK

### completion
def completion_log_files(data, completion_item, buffer, completion):
	global home_dir
	for log in dir_list(home_dir):
		weechat.hook_completion_list_add(completion, log[len(home_dir):], 0, weechat.WEECHAT_LIST_POS_SORT)
	return WEECHAT_RC_OK

def completion_egrep_args(data, completion_item, buffer, completion):
	for arg in ('count', 'all', 'matchcase', 'hilight', 'exact', 'head', 'tail', 'number'):
		weechat.hook_completion_list_add(completion, '--' + arg, 0, weechat.WEECHAT_LIST_POS_SORT)
	return WEECHAT_RC_OK

### Main
def script_init():
	global home_dir
	home_dir = get_home()

if weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, \
		SCRIPT_DESC, '', ''):
	script_init()
	weechat.hook_command(SCRIPT_COMMAND, cmd_grep.__doc__,
			"[[log <file>] | [buffer <name>]] [-a|--all] [-c|--count] [-m|--matchcase] "
			"[-H|--hilight] [-e|--exact] [(-h|--head)|(-t|--tail) [-n|--number <n>]] <expression>",
			# help
			"      log <file>: Search in one log that matches <file> in the logger path. Use '*' and '?' as jokers.\n"
			"   buffer <name>: Search in buffer <name>, if there's no buffer with <name> it will try to search for a log file.\n"
			"       -a, --all: Search in all open buffers.\n"
			"                  If used with 'log <file>' search in all logs that matches <file>.\n"
			"     -c, --count: Just count the number of matched lines instead of showing them.\n"
			" -m, --matchcase: Don't do case insensible search.\n"
			"   -H, --hilight: Colour exact matches in output buffer.\n"
			"     -e, --exact: Print exact matches only.\n"
			"      -t, --tail: Print the last 10 matching lines.\n"
			"      -h, --head: Print the first 10 matching lines.\n"
			"-n, --number <n>: Overrides default number of lines for --tail or --head.\n"
			"    <expression>: Expression to search.\n\n"
			"egrep buffer input:\n"
			"  Repeat last search using the new given expression.\n\n"
			"see http://docs.python.org/lib/re-syntax.html for documentation about python regular expressions.\n",
			# completion template
			"buffer %(buffers_names) %(egrep_arguments)|%*"
			"||log %(egrep_log_files) %(egrep_arguments)|%*"
			"||%(egrep_arguments)|%*",
			'cmd_grep' ,'')
	weechat.hook_command('logs', cmd_logs.__doc__, "[-s|--size] [<filter>]",
			"-s|--size: Sort logs by size.\n"
			" <filter>: Only show logs that match <filter>. Use '*' and '?' as jokers.", '--size', 'cmd_logs', '')
	weechat.hook_completion('egrep_log_files', "list of log files",
			'completion_log_files', '')
	weechat.hook_completion('egrep_arguments', "list of arguments",
			'completion_egrep_args', '')
	# settings
	for opt, val in settings:
		if not weechat.config_is_set_plugin(opt):
			weechat.config_set_plugin(opt, val)
	# colors
	colors = {
			'date': weechat.color('brown'),
			'script_nick': weechat.color('lightgreen'),
			'info': weechat.color('cyan'),
			'hilight': weechat.color('lightred'),
			'reset': weechat.color('reset'),
			}

# vim:set shiftwidth=4 tabstop=4 noexpandtab textwidth=100:
