#!/usr/bin/env python
#coding: utf-8

import os
import sys
import json
import getpass
import commands
import argparse
import ConfigParser

import jinja2


PROGRAMS_DIR = 'programs'
SOURCES_DIR = 'sources'
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
    parser_status    = subparsers.add_parser('status', help='Show application status')

    parser_init.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Supervisord config file(template) path.')
    parser_init.add_argument('-d', '--dir', metavar='DIR', required=True, help='Where you place dealer files.')
    parser_destory.add_argument('-d', '--dir', metavar='DIR', default=None, help='(optional) Where you place dealer files.')
    parser_uninstall.add_argument('-p', '--prog_name', metavar='STRING', required=True, help='Specific by program name')
    # parser_uninstall.add_argument('-c', '--cfg', metavar='FILE', help='Program config file path.')
    parser_uninstall.add_argument('--drop', metavar='y/n', choices=['y', 'n'], default='n', help='If should drop database, default: NO')
    parser_status.add_argument('-m', '--marker', metavar='[program]/all', default='all', help='Show application status')

    for p in (parser_install, parser_update):
        p.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Program config file path.')
    
    for p in (parser_init, parser_destory, parser_install, parser_uninstall, parser_update, parser_status):
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

    def reset(self):
        Permit.last = None

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


def print_step(msg, level=1):
    format_dict = {
        0 : ' * %s',
        1 : '  * .. %s',
        2 : '   * .... %s',
    }
    print format_dict[level] % msg
    
def check_path(path, should_dir=False, should_exists=False):
    path_exists = os.path.exists(path)
    path_is_dir = os.path.isdir(path)

    if should_dir and not path_is_dir:
        raise ValueError('Path is not directory: {}'.format(path))
    elif not should_dir and path_is_dir:
        raise ValueError('Path is directory: {}'.format(path))
    
    if should_exists and not path_exists:
        raise ValueError('Path not exists: {}'.format(path))
    elif not should_exists and path_exists:
        raise ValueError('Path already exists: {}'.format(path))
    
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
        # conf = parse_conf(self.args.target)
        print_step('>>> Started')
        getattr(self, self.action)()

    def init(self):
        """ See: Supervisor.init() """
        Supervisor(self.args.target).init(self.args.dir, self.args.cfg)

    def destory(self):
        """ See: Supervisor.destory() """
        dealer_dir = Supervisor.get_directory(target=self.args.target)
        sources_dir = os.path.join(dealer_dir, SOURCES_DIR)
        for prog_cfg_name in os.listdir(sources_dir):
            prog_name = prog_cfg_name.rsplit('.', 1)[0]
            args = argparse.Namespace(target=self.args.target, prog_name=prog_name)
            print_step('Uninstall program {}'.format(prog_name), level=0)
            Dealer('uninstall', args).uninstall()
        print_step('Destory supervisor', level=0)
        Supervisor(self.args.target).destory()

    def install(self):
        """
        Steps:
        ======
          * Parse supervisord directory from /etc/supervisord.conf
          * Copy [app].conf to [dealer-dir]/sources/
          * Install program to supervisord
          * (optional) Install to nginx
          * (optional) Install to firewall
          * (optional) Init database: create database, create tables, other SQL.
        """
        prog_conf = parse_conf(self.args.cfg)
        prog_name = parse_programs(prog_conf)[0]

        dealer_dir = Supervisor.get_directory(target=self.args.target)
        src_cfg_path = os.path.join(dealer_dir, SOURCES_DIR, '{}.conf'.format(prog_name))
        print_step('Copy dealer file: {} ==> {}'.format(self.args.cfg, src_cfg_path))
        os.system('cp {} {}'.format(self.args.cfg, src_cfg_path))
        
        section_program = prog_conf.items('program:{}'.format(prog_name))
        supervisor = Supervisor(self.args.target)
        supervisor.install(prog_name, section_program)

        if prog_conf.has_section('nginx'):
            kwargs = dict(prog_conf.items('nginx'))
            conf_dir      = kwargs.pop('config_directory')
            link_conf_dir = kwargs.pop('link_config_directory', None)
            command       = kwargs.pop('command', None)
            conf_tmpl     = kwargs.pop('config_template', None)
            nginx = Nginx(kwargs, conf_dir, link_conf_dir, command, conf_tmpl)
            nginx.install()

        if prog_conf.has_section('firewall'):
            kwargs = dict(prog_conf.items('firewall'))
            driver = kwargs.pop('driver')
            firewall = Firewall(driver, kwargs)
            firewall.install()

        if prog_conf.has_section('database'):
            kwargs = dict(prog_conf.items('database'))
            driver = kwargs.pop('driver')
            database = Database(driver, kwargs)
            database.create()

    def uninstall(self):
        """
        Steps:
        ======
          * Parse supervisord directory from /etc/supervisord.conf
          * Uninstall program from supervisord
          * (optional) Uninstall from nginx
          * (optional) Uninstall from firewall
          * Database: you can drop the database if you want !!!
        """
        dealer_dir = Supervisor.get_directory(target=self.args.target)
        src_cfg_path = os.path.join(dealer_dir, SOURCES_DIR, '{}.conf'.format(self.args.prog_name))
        if not os.path.exists(src_cfg_path):
            raise ValueError('Source dealer config file not exists: {}'.format(src_cfg_path))

        prog_conf = parse_conf(src_cfg_path)
        supervisor = Supervisor(self.args.target)
        supervisor.uninstall(self.args.prog_name)
        
        if prog_conf.has_section('nginx'):
            kwargs = dict(prog_conf.items('nginx'))
            conf_dir      = kwargs.pop('config_directory')
            link_conf_dir = kwargs.pop('link_config_directory', None)
            command       = kwargs.pop('command', None)
            nginx = Nginx(kwargs, conf_dir, link_conf_dir, command)
            nginx.uninstall()

        if prog_conf.has_section('firewall'):
            kwargs = dict(prog_conf.items('firewall'))
            driver = kwargs.pop('driver')
            firewall = Firewall(driver, kwargs)
            firewall.uninstall()

        if prog_conf.has_section('database') and self.args.drop.lower() == 'y':
            kwargs = dict(prog_conf.items('database'))
            driver = kwargs.pop('driver')
            database = Database(driver, kwargs)
            database.drop()

        print_step('Remove program config file: {}'.format(src_cfg_path))
        os.remove(src_cfg_path)

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

    def status(self):
        dealer_dir = Supervisor.get_directory(target=self.args.target)
        progs_dir = os.path.join(dealer_dir, PROGRAMS_DIR)
        if self.args.marker == 'all':
            print 'Programs: {%s}' % ', '.join([prog_file.rsplit('.', 1)[0]
                                                for prog_file in os.listdir(progs_dir)])
        else:
            prog_conf_file = os.path.join(progs_dir, '{}.conf'.format(self.args.marker))
            conf = parse_conf(prog_conf_file)
            print json.dumps(dict([(sec, dict(conf.items(sec)))
                                   for sec in conf.sections()]), indent=4)
        print '-' * 72
        supervisor = Supervisor(self.args.target)
        supervisor.status(self.args.marker)


class Supervisor(object):
    
    def __init__(self, target):
        self.target = target

    @staticmethod
    def get_directory(target=None, conf=None):
        """ The supervisord directory actually dealer directory. """
        
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
        sources_dir = os.path.join(directory, SOURCES_DIR)
        print_step('Make dirs: {}, {}'.format(programs_dir, sources_dir))
        os.makedirs(programs_dir)
        os.makedirs(sources_dir)
    
        print_step('Write supervisord.conf to %s' % self.target)
        with open(source_tmpl, 'r') as f:
            template = jinja2.Template(f.read())
            template.stream(directory=directory).dump(self.target)
    
        print_step('Start supervisord')
        os.system('supervisord -c {}'.format(self.target))

    def destory(self):
        """
        Steps:
        ======
          * Uninstall all programs
          * Shutdown supervisord
          * Remove supervisord(dealer) directory
          * Remove /etc/supervisord.conf
        """
        directory = Supervisor.get_directory(self.target)
        check_path(directory, should_dir=True, should_exists=True)
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
        directory = Supervisor.get_directory(self.target)
        conf_path = os.path.join(directory, PROGRAMS_DIR, '{}.conf'.format(prog_name))
        check_path(conf_path, should_exists=False)
        conf = ConfigParser.RawConfigParser()
        section_name = 'program:{}'.format(prog_name)
        conf.add_section(section_name)
        for key, value in section:
            conf.set(section_name, key, value)
            
        print_step('Write supervisord config file to: {}'.format(conf_path))
        with open(conf_path, 'w') as fd:
            conf.write(fd)
        self.reload()

    def uninstall(self, prog_name):
        """
        Steps:
        ======
          * Stop the program
          * Remove [app-dealer]/programs/[app].conf file
        """
        directory = Supervisor.get_directory(self.target)
        conf_path = os.path.join(directory, PROGRAMS_DIR, '{}.conf'.format(prog_name))
        check_path(conf_path, should_exists=True)
        self.stop(prog_name)
        print_step('Remove supervisord config file: {}'.format(conf_path))
        os.remove(conf_path)
        self.reload()

    def update(self):
        pass

    def stop(self, marker):
        """ marker = {[program], all} """
        print_step('Supervisor stop: {}'.format(marker))
        os.system('supervisorctl -c {} stop {}'.format(self.target, marker))

    def status(self, marker):
        os.system('supervisorctl -c {} status {}'.format(self.target, marker))
        
    def reload(self):
        print_step('Update supervisord for config change')
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

    @property
    def conf_filename(self):
        server_name_str = '-'.join(self.kwargs['server_name'].split())
        return '{}-{}.conf'.format(server_name_str, self.kwargs['listen'])
        
    def install(self):
        filename = self.conf_filename
        file_path = os.path.join(self.conf_dir, filename)
        check_path(file_path, should_exists=False)
        
        ngx_tmpl = NGX_SERVER_TMPL
        if self.conf_tmpl:
            print_step('Read nginx config template from: {}'.format(self.conf_tmpl))
            with open(self.conf_tmpl, 'r') as f:
                ngx_tmpl = f.read()
        print_step('Write nginx config file to: {}'.format(file_path))
        jinja2.Template(ngx_tmpl).stream(**self.kwargs).dump(file_path)
    
        if self.link_conf_dir:
            file_link = os.path.join(self.link_conf_dir, filename)
            print_step('Make symbol link to: {}'.format(file_link))
            os.symlink(file_path, file_link)
        self.reload()
    
    def uninstall(self):
        filename = self.conf_filename
        file_path = os.path.join(self.conf_dir, filename)
        check_path(file_path, should_exists=True)
        print_step('Remove nginx config file: {}'.format(file_path))
        os.remove(file_path)
        if self.link_conf_dir:
            file_link = os.path.join(self.link_conf_dir, filename)
            print_step('Unlink symbol link: {}'.format(file_link))
            os.unlink(file_link)
        self.reload()
        
    def update(self):
        pass

    def reload(self):
        print_step('Reload nginx')
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

def main():
    args = parse_args()
    print args
    print '='*72
    assert getpass.getuser() == 'root', 'Permission denied!'
    try:
        check_args(args)
        Dealer(args.action, args).process()
        print '='*72
        print '>>> DONE!'
    except ValueError as e:
        print '[ERROR] :: %r' % e


if __name__ == '__main__':
    main()
