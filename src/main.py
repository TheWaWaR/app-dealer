#!/usr/bin/env python
#coding: utf-8

import os
import sys
import getpass
import argparse
import ConfigParser

import jinja2

PROGRAMS_DIR = 'programs'
NGX_SERVER_TMPL = '''
server {
    listen       {{ listen }};
    server_name  {{ server_name }};

    location {{ location }} {
        proxy_pass {{ proxy_pass }};
    }
}
'''


def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='action')
    parser_init      = subparsers.add_parser('init', help='Init the app dealer')
    parser_destory   = subparsers.add_parser('destory', help='Remove the app dealer files')
    parser_install   = subparsers.add_parser('install', help='Install the application')
    parser_uninstall = subparsers.add_parser('uninstall', help='Uninstall the application')
    parser_update    = subparsers.add_parser('update', help='Update the application')

    parser_init.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Supervisord config file(template) path.')
    parser_init.add_argument('-d', '--dir', metavar='DIR', required=True, help='Where you place dealer files.')
    parser_destory.add_argument('-d', '--dir', metavar='DIR', default=None, help='(optional) Where you place dealer files.')
        
    for p in (parser_install, parser_uninstall, parser_update):
        p.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Program config file path.')
    
    for p in (parser_init, parser_destory, parser_install, parser_uninstall, parser_update):
        p.add_argument('-t', '--target', metavar='FILE', default='/etc/supervisord.conf',
                       help='(optional) Target global supervisord config file')

    args = parser.parse_args()
    return args

class Permit(object):
    """ Ask the user whether can continue actions.
    
    Example:
    ========
       $ Can I continue doing things? [Y/N/A]:
    
    """
    last = None
    
    def __init__(self, msg):
        self.msg = msg

    @staticmethod
    def reset():
        Permit.last = None

    def reset(self):
        Permit.reset()

    def check(self, y=True, n=True, All=False):
        if Permit.last == 'a':
            return True

        options = filter(lambda opt: opt[0], [(y, 'Y'), (n, 'N'), (All, 'A')])
        option_answers = [opt[1].lower() for opt in options]
        options_msg = '[{}]'.format('/'.join([opt[1] for opt in options]))
        answer = None
        while answer not in option_answers:
            answer = raw_input('{} {}:'.format(self.msg, options_msg)).lower()

        if answer == 'n':
            print >> sys.stderr, '[Abort]'
            sys.exit(-1)
        Permit.last = answer


def print_step(msg):
    print '  * .... %s' % msg
    
# ==============================================================================
#  ConfigParser stuffs
# ==============================================================================
def parse_programs(conf):
    return [section.split(':')[1] for section in conf.sections()
            if section.startswith('program:')]

def parse_include(path, files):
    lst = []
    cmd = 'cd %s && ls %s' % (path, files)
    output = commands.getoutput(cmd)
    for sub_name in output.split('\n'):
        sub_path = os.path.join(path, sub_name)
        sub_conf = parse_conf(sub_path)
        lst.extend(parse_programs(sub_conf))
    return lst

def parse_conf(path):
    conf = ConfigParser.RawConfigParser()
    conf.read(path)
    return conf


# ==============================================================================
#  Config (nginx, supervisor, firewall) things.
# ==============================================================================
class Dealer(object):

    def __init__(self, action, args):
        self.action = action
        self.args = args

    def process(self):
        conf = parse_conf(self.args.target)
        getattr(self, self.action)()

    def init(self):
        """ See: Supervisor.init() """
        Supervisor(self.args.target).init(self.args.dir, self.args.cfg)

    def destory(self):
        """ See: Supervisor.destory() """
        Supervisor(self.args.target).destory(self.args.dir)

    def install(self):
        """
        Steps:
        ======
          * Parse supervisord directory from /etc/supervisord.conf
          * Copy [APP].conf to [supervisord-dir]/programs/
          * (optional) Add config to nginx
          * (optional) Add config to firewall
          * (optional) Init database: create database, create tables, other SQL.
          * Reload supervisord
          * Reload nginx
        """
        conf = parse_conf(self.args.cfg)
        prog_name = parse_programs(conf)[0]
        section_program = conf.items('program:{}'.format(prog_name))
        supervisor = Supervisor(self.args.target)
        supervisor.install(prog_name, section_program)

        nginx, firewall, database = None, None, None
        if conf.has_section('nginx'):
            kwargs = dict(conf.items('nginx'))
            conf_dir      = kwargs.pop('config_directory')
            link_conf_dir = kwargs.pop('link_config_directory', None)
            command       = kwargs.pop('command', None)
            conf_tmpl     = kwargs.pop('config_template', None)
            nginx = Nginx(kwargs, conf_dir, link_conf_dir, command, conf_tmpl)
            nginx.install()

        if conf.has_section('firewall'):
            kwargs = dict(conf.items('firewall'))
            driver = kwargs.pop('driver')
            firewall = Firewall(driver, kwargs)
            firewall.install()

        if conf.has_section('database'):
            kwargs = dict(conf.items('database'))
            driver = kwargs.pop('driver')
            database = Database(driver, kwargs)
            database.create()

        print_step('Reload supervisor and nginx!')
        [service.reload() for service in [supervisor, nginx] if service]

    def uninstall(self):
        """
        Steps:
        ======
          * Parse supervisord directory from /etc/supervisord.conf
          * Remove [APP].conf from [supervisord-dir]/programs/
          * (optional) Remove config from nginx
          * (optional) Remove config from firewall
          * Database: do not do anything !!!
          * Reload supervisord
          * Reload nginx
        """

    def update(self):
        """
        Steps:
        ======
          * Parse supervisord directory from /etc/supervisord.conf
          * Update [supervisord-dir]/programs/[APP].conf
          * (if needed) Update config from nginx
          * (if needed) Update config from firewall
          * Database: ??? HOW ???
          * (if needed) Reload supervisord
          * (if needed) Reload nginx 
        """

class Supervisor(object):
    
    def __init__(self, target):
        self.target = target

    @staticmethod
    def get_directory(target=None, conf=None):
        if not conf:
            conf = parse_conf(target)
        directory = None
        for section, item in (('unix_http_server', 'file'), ('supervisord', 'pidfile')):
            try:
                sock_file = conf.get(section, item)
                directory, _ = os.path.split(sock_file)
                break
            except ConfigParser.NoSectionError:
                pass
        if directory is None:
            raise ValueError('Can not find the dealer directory!')
        return directory
        
    # def get_directory(self):
    #     return Supervisor.get_directory(self.target)

    def get_programs(self):
        conf = parse_conf(self.target)
        programs = parse_programs(conf)
        try:
            files = conf.get('include', 'files')
            s_path, s_name = os.path.split(self.target)
            programs.extend(parse_include(s_path, files))
        except ConfigParser.NoSectionError:
            pass
        return programs

    def init(self, directory, source_tmpl):
        """
        Steps:
        ======
          * Create supervisord directories
          * Write supervisord.conf to `args.target` (default: /etc/supervisord.conf)
          * Start supervisord
        """
        programs_dir = os.path.join(directory, PROGRAMS_DIR)
        print_step('Make dirs: %s' % programs_dir)
        os.makedirs(programs_dir)
    
        print_step('Write supervisord.conf to %s' % self.target)
        with open(source_tmpl, 'r') as f:
            template = jinja2.Template(f.read())
            template.stream(directory=directory).dump(self.target)
    
        print_step('Start supervisord')
        os.system('supervisord -c {}'.format(self.target))


    def destory(self, directory=None):
        """
        Steps:
        ======
          * Uninstall all programs
          * Shutdown supervisord
          * Remove supervisord(dealer) directory
          * Remove /etc/supervisord.conf
        """
        if not directory:
            directory = Supervisor.get_directory(self.target)
        if not os.path.exists(directory):
            raise ValueError('Supervisord(dealer) directory %s not found!' % directory)
        Permit('''
        1. Shutdown supervisord;
        2. remove supervisord(dealer) directory: {};
        3. Remove supervisord config file: {}
        >> ? '''.format(directory, self.target)).check()
        print_step('Shutdown supervisord')
        os.system('supervisorctl -c {} shutdown'.format(self.target))
        
        print_step('Remove supervisord(dealer) directory: %s' % directory)
        os.system('rm -r {}'.format(directory))
        
        print_step('Remove supervisord config file: %s' % self.target)
        os.remove(self.target)

    def install(self, prog_name, section):
        conf = ConfigParser.RawConfigParser()
        section_name = 'program:{}'.format(prog_name)
        conf.add_section(section_name)
        for key, value in section:
            conf.set(section_name, key, value)
            
        directory = Supervisor.get_directory(self.target)
        conf_path = os.path.join(directory, PROGRAMS_DIR, '{}.conf'.format(prog_name))
        with open(conf_path, 'w') as fd:
            conf.write(fd)

    def uninstall(self):
        pass
    def update(self):
        pass

    def reload(self):
        os.system('supervisorctl -c {} update'.format(self.target))


class Nginx(object):
    def __init__(self, kwargs, conf_dir, link_conf_dir=None, command=None, conf_tmpl=None):
        if not command:
            commands = filter(os.path.exists, ['/sbin/nginx', '/bin/nginx',
                                               '/usr/sbin/nginx', '/usr/bin/nginx',
                                               '/usr/local/sbin/nginx', '/usr/local/bin/nginx'])
            if commands:
                defaults['command'] = commands[0]
            else:
                raise ValueError('Nginx not found!')
        for key, value in (('listen'      , '80'),
                           ('server_name' , '_'),
                           ('location'    , '/')):
            kwargs.setdefault(key, value)

        self.kwargs = kwargs
        self.conf_dir = conf_dir
        self.link_conf_dir = link_conf_dir
        self.command = command
        self.conf_tmpl = conf_tmpl
        
    def install(self):
        server_name_str = '-'.join(self.kwargs['server_name'].split())
        filename = '{}-{}.conf'.format(server_name_str, self.kwargs['listen'])
        file_path = os.path.join(self.conf_dir, filename)

        ngx_tmpl = NGX_SERVER_TMPL
        if self.conf_tmpl:
            with open(self.conf_tmpl, 'r') as f:
                ngx_tmpl = f.read()
        jinja2.Template(ngx_tmpl).stream(**self.kwargs).dump(file_path)
    
        if self.link_conf_dir:
            file_link = os.path.join(self.link_conf_dir, filename)
            os.system('ln -s %(file_path)s %(file_link)s' % locals())
    
    def uninstall(self):
        pass
        
    def update(self):
        pass

    def reload(self):
        os.system('{} -s reload'.format(self.command))


class Firewall(object):
    def __init__(self, driver, kwargs):
        pass
    def install(self):
        pass
    def uninstall(self):
        pass


class Database(object):
    def __init__(self, driver, kwargs): pass
    def create(self): pass
    def drop(self): pass
    
# ==============================================================================
#  Main functions
# ==============================================================================
def check_args(args):
    """ Check arguments for all actions. """
    
    if args.action == 'init':
        if os.path.exists(args.dir):
            raise ValueError('Dealer directory %s already exists!' % args.dir)
        if os.path.exists(args.target):
            raise ValueError('Target file %s already exists' % args.target)

    if args.action == 'destory':
        if not os.path.exists(args.target):
            raise ValueError('Target file %s not found' % args.target)

    if args.action in ('init', 'install', 'uninstall', 'update'):
        if not os.path.isfile(args.cfg):
            raise ValueError('Invalid config file: %s' % args.cfg)


def main():
    args = parse_args()
    print args
    print '='*40
    assert getpass.getuser() == 'root', 'Permission denied!'
    try:
        check_args(args)
        Dealer(args.action, args).process()
        print '='*40
        print '>>> DONE!'
    except ValueError as e:
        print '[ERROR] :: %r' % e


if __name__ == '__main__':
    main()
