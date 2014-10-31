#!/usr/bin/env python
#coding: utf-8

import os
import sys
import getpass
import argparse
import ConfigParser

import jinja2


def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='action')
    parser_init      = subparsers.add_parser('init', help='Init the app dealer')
    parser_destory   = subparsers.add_parser('destory', help='Remove the app dealer files')
    parser_install   = subparsers.add_parser('install', help='Install the application')
    parser_uninstall = subparsers.add_parser('uninstall', help='Uninstall the application')
    parser_update    = subparsers.add_parser('update', help='Update the application')

    parser_init.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Supervisord config file(template) path.')
    parser_init.add_argument('-d', '--dir', metavar='DIR', required=True, help='Where you place supervisord files.')
        
    for p in (parser_install, parser_uninstall, parser_update):
        p.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Program config file path.')
    
    for p in (parser_init, parser_destory, parser_install, parser_uninstall, parser_update):
        p.add_argument('-t', '--target', metavar='FILE', default='/etc/supervisord.conf',
                       help='(optional) Target global supervisord config file')

    args = parser.parse_args()
    return args

class Permit(object):
    """ Ask the user whether can continue actions.
    
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
def get_programs(conf_path):
    conf = parse_conf(conf_path)
    programs = parse_programs(conf)
    try:
        files = conf.get('include', 'files')
        s_path, s_name = os.path.split(conf_path)
        programs.extend(parse_include(s_path, files))
    except ConfigParser.NoSectionError:
        pass
    return programs

def parse_programs(conf):
    lst = []
    for section in conf.sections():
        if section.startswith('program:'):
            lst.append(section.split(':')[1])
    return lst

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
def cfg_nginx(ngx_kwargs, directory, link_directory=None, tmpl_file=None):
    ngx_tmpl = '''
    server {
        listen       {{ listen }};
        server_name  {{ server_name }};
    
        location {{ location }} {
            proxy_pass {{ proxy_pass }};
        }
    }
    '''
    filename = '%(server_name)s_%(listen)s.conf' % ngx_kwargs
    file_path = os.path.join(directory, filename)
    if tmpl_file:
        with open(tmpl_file, 'r') as f:
            ngx_tmpl = f.read()
    jinja2.Template(ngx_tmpl).stream(**ngx_kwargs).dump(file_path)

    if link_directory:
        file_link = os.path.join(link_directory, filename)


def cfg_supervisor(): pass
def cfg_firewall(): pass

def decfg_nginx(): pass
def decfg_firewall(): pass
def decfg_supervisor(): pass

# ==============================================================================
#  Init databases
# ==============================================================================
def init_db_postgres(): pass
def init_db_mysql(): pass
def init_db_sqlite(): pass
def init_db():
    driver_map = {
        'postgres' : init_db_postgres,
        'mysql'    : init_db_mysql,
        'sqlite'   : init_db_sqlite
    }


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

def get_dealer_dir(target):
    conf = parse_conf(target)
    dealer_dir = None
    for section, item in (('unix_http_server', 'file'), ('supervisord', 'pidfile')):
        try:
            sock_file = conf.get(section, item)
            dealer_dir, _ = os.path.split(sock_file)
            break
        except ConfigParser.NoSectionError:
            pass
    if dealer_dir is None:
        raise ValueError('Can not find the dealer directory!')
    return dealer_dir


def init(args):
    """
    Steps:
    ======
      * Create supervisord directories
      * Write supervisord.conf to `args.target` (default: /etc/supervisord.conf)
      * Start supervisord
    """
    supervisord_dir = os.path.join(args.dir, 'programs')
    print_step('Make dirs: %s' % supervisord_dir)
    os.makedirs(supervisord_dir)

    print_step('Write supervisord.conf to %s' % args.target)
    with open(args.cfg, 'r') as f:
        template = jinja2.Template(f.read())
        template.stream(dir=args.dir).dump(args.target)

    print_step('Start supervisord')
    os.system('supervisord -c {}'.format(args.target))


def destory(args):
    """
    Steps:
    ======
      * Uninstall all programs
      * Shutdown supervisord
      * Remove dealer directory
      * Remove /etc/supervisord.conf
    """
    dealer_dir = get_dealer_dir(args.target)
    if not os.path.exists(dealer_dir):
        raise ValueError('Dealer directory %s not found!' % dealer_dir)
    Permit('''    1. Shutdown supervisord;
    2. remove dealer directory: {};
    3. Remove supervisord config file: {}
    >> ? '''.format(dealer_dir, args.target)).check()
    print_step('Shutdown supervisord')
    os.system('supervisorctl -c {} shutdown'.format(args.target))
    
    print_step('Remove dealer directory: %s' % dealer_dir)
    os.system('rm -r {}'.format(dealer_dir))
    
    print_step('Remove supervisord config file: %s' % args.target)
    os.remove(args.target)


def install(args):
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
    conf = parse_conf(args.target)
    


def uninstall(args):
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
    pass


def update(args):
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
    pass


def main():
    args = parse_args()
    print args
    print '='*40
    assert getpass.getuser() == 'root', 'Permission denied!'
    try:
        check_args(args)
        globals()[args.action](args)
        print '='*40
        print '>>> DONE!'
    except ValueError as e:
        print '[ERROR] :: %r' % e


if __name__ == '__main__':
    main()
