#!/usr/bin/env python
#coding: utf-8

import os
import sys
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

    parser_init.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Supervisord config file path.')
    
    for p in (parser_init, parser_destory):
        p.add_argument('-d', '--dir', metavar='DIR', required=True, help='Where you place supervisord files.')
        p.add_argument('-t', '--target', metavar='FILE', default='/etc/supervisord.conf', help='Target global supervisord config file')
        
    for p in (parser_install, parser_uninstall, parser_update):
        p.add_argument('-c', '--cfg', metavar='FILE', required=True, help='Program config file path.')

    args = parser.parse_args()
    return args

def print_step(msg):
    print '  * %s ...' % msg
    
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


def build_nginx_cfg(): pass
def build_supervisor_cfg(): pass

def cfg_supervisor(): pass
def cfg_nginx(): pass
def cfg_firewall(): pass

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
            raise ValueError('Directory %s already exists!' % args.dir)
        if os.path.exists(args.target):
            raise ValueError('Target file %s already exists' % args.target)

    if args.action in ('init', 'install', 'uninstall', 'update'):
        if not os.path.isfile(args.cfg):
            raise ValueError('Invalid config file: %s' % args.cfg)

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
    os.system('supervisord')


def destory(args):
    """
    Steps:
    ======
      * Uninstall all programs
      * Stop supervisord
      * Remove all supervisord directories
      * Remove /etc/supervisord.conf
    """
    pass

def install(args):
    """
    Steps:
    ======
      * Parse supervisord directory from /etc/supervisord.conf
      * Put [APP].conf to [supervisord-dir]/programs/[APP].conf
      * (optional) Add config to nginx
      * (optional) Add config to firewall
      * (optional) Init database: create database, create tables, other SQL.
      * Reload supervisord
      * Reload nginx
    """
    pass


def uninstall(args):
    """
    Steps:
    ======
      * Parse supervisord directory from /etc/supervisord.conf
      * Remove [supervisord-dir]/programs/[APP].conf
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
    check_args(args)
    globals()[args.action](args)
    print '>>> DONE!'


if __name__ == '__main__':
    main()
