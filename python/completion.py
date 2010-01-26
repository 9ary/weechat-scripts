# -*- coding: utf-8 -*-
###
# Copyright (c) 2010 by Elián Hanisch <lambdae2@gmail.com>
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
#
#   This scripts adds word completion, like irssi's /completion
#
#   Commands:
#   * /completion: see /help completion
#
#
#   Settings:
#   * plugins.var.python.completion.replace_values:
#     Completion list, it shouldn't be edited by hand.
#
#
#   History:
#   2010-01-26
#   version 0.1: release
#
###

try:
    import weechat
    WEECHAT_RC_OK = weechat.WEECHAT_RC_OK
    import_ok = True
except ImportError:
    print "This script must be run under WeeChat."
    print "Get WeeChat now at: http://www.weechat.org/"
    import_ok = False

SCRIPT_NAME    = "completion"
SCRIPT_AUTHOR  = "Elián Hanisch <lambdae2@gmail.com>"
SCRIPT_VERSION = "0.1"
SCRIPT_LICENSE = "GPL3"
SCRIPT_DESC    = "Word completions for WeeChat"
SCRIPT_COMMAND = "completion"

completion_template = 'completion_script'

### Config ###
settings = {
'replace_values':''
}

### Messages ###
def debug(s, prefix='', buffer=None):
    """Debug msg"""
    if not weechat.config_get_plugin('debug'): return
    if buffer is None:
        buffer_name = 'DEBUG_' + SCRIPT_NAME
        buffer = weechat.buffer_search('python', buffer_name)
        if not buffer:
            buffer = weechat.buffer_new(buffer_name, '', '', '', '')
            weechat.buffer_set(buffer, 'nicklist', '0')
            weechat.buffer_set(buffer, 'time_for_each_line', '0')
            weechat.buffer_set(buffer, 'localvar_set_no_log', '1')
    weechat.prnt(buffer, '%s\t%s' %(prefix, s))

def error(s, prefix=None, buffer='', trace=''):
    """Error msg"""
    prefix = prefix or script_nick
    weechat.prnt(buffer, '%s%s %s' %(weechat.prefix('error'), prefix, s))
    if weechat.config_get_plugin('debug'):
        if not trace:
            import traceback
            if traceback.sys.exc_type:
                trace = traceback.format_exc()
        not trace or weechat.prnt('', trace)

def say(s, prefix=None, buffer=''):
    """normal msg"""
    prefix = prefix or script_nick
    weechat.prnt(buffer, '%s\t%s' %(prefix, s))

print_replace = lambda k,v : say('%s %s=>%s %s' %(k, color_delimiter, color_reset, v))

### Config functions ###
def get_config_dict(config):
    value = weechat.config_get_plugin(config)
    if not value:
        return {}
    values = value.split(';;')
    values = map(lambda s: s.split('=>'), values)
    #debug(values)
    return dict(values)

def load_replace_table():
    global replace_table
    replace_table = get_config_dict('replace_values')

def save_replace_table():
    global replace_table
    values = [ '%s=>%s' %(k, v) for k, v in replace_table.iteritems() ]
    weechat.config_set_plugin('replace_values', ';;'.join(values))

### Commands ###
def cmd_completion(data, buffer, args):
    global replace_table
    if not args:
        if replace_table:
            for k, v in replace_table.iteritems():
                print_replace(k, v)
        else:
            say('No completions.')
        return WEECHAT_RC_OK
    cmd, space, args = args.partition(' ')
    if cmd == 'add':
        word, space, text = args.partition(' ')
        k, v = word.strip(), text.strip()
        replace_table[k] = v
        save_replace_table()
        say('added: %s %s=>%s %s' %(k, color_delimiter, color_reset, v))
    elif cmd == 'del':
        k = args.strip()
        try:
            del replace_table[k]
            save_replace_table()
            say("completion for '%s' deleted." %k)
            save_replace_table()
        except KeyError:
            error("completion for '%s' not found." %k)
    return WEECHAT_RC_OK

### Completion ###
def completion_replacer(data, completion_item, buffer, completion):
    global replace_table
    input = weechat.buffer_get_string(buffer, 'input')
    input, space, last_word = input.rpartition(' ')
    if last_word in replace_table:
        weechat.buffer_set(buffer, 'input', '%s%s%s ' %(input, space, replace_table[last_word]))
    return WEECHAT_RC_OK

def completion_keys(data, completion_item, buffer, completion):
    global replace_table
    for k in replace_table:
        weechat.hook_completion_list_add(completion, k, 0, weechat.WEECHAT_LIST_POS_SORT)
    return WEECHAT_RC_OK

### Main ###
if __name__ == '__main__' and import_ok and \
        weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE, \
        SCRIPT_DESC, '', ''):
    
    # colors
    color_delimiter   = weechat.color('chat_delimiters')
    color_script_nick = weechat.color('chat_nick')
    color_reset   = weechat.color('reset')
    
    # pretty [SCRIPT_NAME]
    script_nick = '%s[%s%s%s]%s' %(color_delimiter, color_script_nick, SCRIPT_NAME, color_delimiter,
            color_reset)

    # settings
    for opt, val in settings.iteritems():
        if not weechat.config_is_set_plugin(opt):
            weechat.config_set_plugin(opt, val)

    load_replace_table()
    
    completion_template = 'completion_script'
    weechat.hook_completion(completion_template,
            "Replaces last word in input by its configured value.", 'completion_replacer', '')
    weechat.hook_completion('completion_keys', "Words in completion list.", 'completion_keys', '')
    
    weechat.hook_command(SCRIPT_COMMAND, SCRIPT_DESC , "[add <word> <text>|del <word>]",
"""
add: adds a new completion, <word> => <text>.
del: deletes a completion.
Without arguments it displays current completions.

<word> will be replaced by <text> when pressing tab,
note that only the last word in input line is completed,
not where the cursor is or in all matching words.

Setup:
For this script to work, you must add the template
%%(%(completion)s) to the default completion template, use:
/set weechat.completion.default_template "%%(nicks)|%%(irc_channels)|%%(%(completion)s)"

Examples:
/%(command)s add wee WeeChat (typing wee<tab> will replace 'wee' by 'WeeChat')
/%(command)s add weeurl http://www.weechat.org/
/%(command)s add test This is a test!
""" %dict(completion=completion_template, command=SCRIPT_COMMAND),
            'add|del %(completion_keys)', 'cmd_completion', '')

# vim:set shiftwidth=4 tabstop=4 softtabstop=4 expandtab textwidth=100:
