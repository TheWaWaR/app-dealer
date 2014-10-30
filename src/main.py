#!/usr/bin/env python
#coding: utf-8

import os
import sys

def parse_args():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-c', '--cfg', metavar='FILE', help='Program config file path.')
    args = parser.parse_args()
    
    return args
    
def parse_cfg(path):
    pass

def build_nginx_cfg(): pass
def build_supervisor_cfg(): pass

def cfg_supervisor(): pass
def cfg_nginx(): pass
def cfg_firewall(): pass
def init_db(): pass

def main():
    args = parse_args()
    print args


if __name__ == '__main__':
    main()
