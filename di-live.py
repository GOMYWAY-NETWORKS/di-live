#!/usr/bin/python
# Copyright (c) 2008 Alon Swartz <alon@turnkeylinux.org> - all rights reserved

"""
Debian Installer Live

Drives the installation, executing components according to alpha-numeric
ordering, and responsible for dynamically assembling the menu and executing
components when they are selected.

Similar to d-i's main-menu, di-live's menu will only be visible when debconf
priority is low or medium. Priority is reduced when a component fails,
and returns to original level when next component completes successfully.

Options:
  -d --debug      Set DEBCONF_DEBUG=developer DEBIAN_FRONTEND=readline

"""

import re
import os
import sys
import getopt
import debconf

from os.path import *

LOGFILE = '/var/log/di-live.log'
def log(s):
    file(LOGFILE, 'a').write(s + "\n")

class Error(Exception):
    pass

class Debian_Priority:
    """class for controlling DEBIAN_PRIORITY"""

    def __init__(self):
        self.original = os.environ.get('DEBIAN_PRIORITY')
        self.current = self.original

    def __del__(self):
        self.revert()

    def get(self):
        return self.current

    def set(self, priority):
        if priority in (None, self.current):
            return

        priorities = ('low', 'medium', 'high', 'critical')
        if priority not in priorities:
            raise Error('illegal debian priority', priority)

        os.environ['DEBIAN_PRIORITY'] = priority
        self.current = priority

    def revert(self):
        """revert priority back to original priority"""
        self.set(self.original)

    def decrease(self):
        """decrease priority to medium (or low if original was low)"""
        if self.original == 'low':
            self.set('low')
        else:
            self.set('medium')

class Menu:
    """class for controlling a debconf menu with choices"""

    def __init__(self, template, title=None, priority='high', subst='CHOICES'):
        debconf.runFrontEnd()
        self.template = template
        self.db = debconf.Debconf(title)

        self.db.capb('backup')
        self.priority = priority
        self.subst = subst

    def __del__(self):
        self.db.stop()

    def display(self, names):
        titles = []
        self.choices = {}
        for name in names:
            title = name.capitalize()
            try:
                template = 'debian-installer/%s/title' % name
                title = self.db.metaget(template, 'description')
            except debconf.DebconfError, e:
                if not e[0] == 10:
                    raise Error('DebconfError', e)

            titles.append(title)
            self.choices[title] = name

        self.db.reset(self.template)
        self.db.subst(self.template, self.subst, ", ".join(titles))
        self.db.input(self.priority, self.template)
        try:
            self.db.go()
        except debconf.DebconfError, e:
            if not e[0] == 30 and not e[1] == "backup":
                raise Error('debconf error', e)

    def get_choice(self):
        ret = self.db.get(self.template)
        if self.choices.has_key(ret):
            return self.choices[ret]
        return ret

class Component:
    """class for managing a component"""

    def __init__(self, path):
        self.path = path
        self.name = re.sub('^[\d]*', '', basename(path))
        self.exitcode = None

    def execute(self):
        error = os.system(self.path)
        if error:
            self.exitcode = os.WEXITSTATUS(error)
            return False

        self.exitcode = 0
        return True

class Components(dict):
    """class for holding components"""

    def __init__(self, dirpath):
        if not exists(dirpath):
            raise Error('non existent components path', dirpath)

        for file in os.listdir(dirpath):
            path = join(dirpath, file)
            if self._is_executable(path):
                self.add(path)

    def __iter__(self):
        """return component in alpha-numeric ordering according to name"""
        keys = self.keys()
        keys.sort()
        for key in keys:
            yield self[key]

    @staticmethod
    def _is_executable(path):
        if os.stat(path).st_mode & 0111 == 0:
            return False
        return True

    def add(self, path):
        if not self._is_executable(path):
            raise Error('component not executable', path)

        name = basename(path)
        self[name] = Component(path)
    
    def remove(self, name):
        del self[name]

class Components_Menu:
    """class to mimic d-i main-menu"""

    def __init__(self, components_dir, menu_template, menu_title=None):
        self.components = Components(components_dir)
        self.menu = Menu(menu_template, menu_title)

        self.priority = Debian_Priority()

    def _get_next_component(self):
        if self.priority.get() in ('low', 'medium'):
            self.menu.display([ c.name for c in self.components ])
            choice = self.menu.get_choice()

            for c in self.components:
                if c.name == choice:
                    return c
        else:
            for c in self.components:
                if basename(c.path) > self.last:
                    return c

        return None

    def run(self):
        self.last = ''
        while 1:
            component = self._get_next_component()
            if component is None:
                break

            component.execute()
            if component.exitcode == 0:
                self.last = basename(component.path)
                self.priority.revert()
            else:
                self.priority.decrease()

def usage(s=None):
    if s:
        print >> sys.stderr, "Error:", s 
    print >> sys.stderr, "Syntax: %s [options]" % sys.argv[0]
    print >> sys.stderr, __doc__
    sys.exit(1)

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "hd", ['help', 'debug'])
    except getopt.GetoptError, e:
        usage(e)

    debug = False
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt in ('-d', '--debug'):
            debug = True

    if debug:
        os.environ['DEBCONF_DEVELOPER'] = 'developer'
        os.environ['DEBIAN_FRONTEND'] = 'readline'

    components_dir = '/usr/lib/di-live.d'
    menu_template = 'di-live/main_menu'
    menu_title = 'Debian Installer Live'

    Components_Menu(components_dir, menu_template, menu_title).run()


if __name__ == "__main__":
    main()

