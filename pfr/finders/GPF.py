import collections
from copy import deepcopy
import json
import os
from pprint import pprint
import requests
import time

import pandas as pd
from pyquery import PyQuery as pq

from pfr import decorators, utils

GAME_PLAY_URL = ('http://www.pro-football-reference.com/'
                 'play-index/play_finder.cgi')

CONSTANTS_FN = 'GPFConstants.json'

def GamePlayFinder(**kwargs):
    """ Docstring will be filled in by __init__.py """

    querystring = kwArgsToQS(**kwargs)
    url = '{}?{}'.format(GAME_PLAY_URL, querystring)
    # if verbose, print url
    if kwargs.get('verbose', False):
        print url
    html = utils.getHTML(url)
    doc = pq(html)
    
    # try to parse
    # try:
    table = doc('#div_ table.stats_table')
    cols = [th.text for th in table('thead tr th[data-stat]')]
    cols[-1] = 'EPDiff'

    data = [
        [
            ''.join(
                [c if isinstance(c, basestring) 
                 else utils.relURLToID(c.attrib['href'])
                 for c in td.contents()]
            )
            for td in map(pq, row('td'))
        ]
        for row in map(pq, table('tbody tr[class=""]'))
    ]

    plays = pd.DataFrame(data, columns=cols, dtype=float)
    # except Exception as e:
    #     # if parsing goes wrong, return empty DataFrame
    #     raise e
    #     return pd.DataFrame(columns=cols)

    plays['Year'] = plays.Date.str[:4].astype(int)
    plays['Month'] = plays.Date.str[4:6].astype(int)
    plays['Date'] = plays.Date.str[6:8].astype(int)
    plays = plays.rename({'Date': 'Boxscore'})
    details = pd.DataFrame(map(utils.parsePlayDetails, plays.Detail))
    plays = pd.merge(plays, details, left_index=True, right_index=True)

    return plays

def kwArgsToQS(**kwargs):
    """Converts kwargs given to GPF to a querystring.

    :returns: the querystring.
    """
    # start with defaults
    inpOptDef = getInputsOptionsDefaults()
    opts = {
        name: dct['value']
        for name, dct in inpOptDef.iteritems()
    }

    # clean up keys and values
    for k, v in kwargs.items():
        # pID, playerID => player_id
        if k.lower() in ('pid', 'playerid'):
            del kwargs[k]
            kwargs['player_id'] = v
        # player_id can accept rel URLs
        if k == 'player_id':
            if v.startswith('/players/'):
                kwargs[k] = utils.relURLToID(v)
        # bool => 'Y'|'N'
        if isinstance(v, bool):
            kwargs[k] = 'Y' if v else 'N'
        # tm, team => team_id
        if k.lower() in ('tm', 'team'):
            del kwargs[k]
            kwargs['team_id'] = v
        # yr_min, yr_max => year_min, year_max
        if k.lower() in ('yr_min', 'yr_max'):
            del kwargs[k]
            if k.lower() == 'yr_min':
                kwargs['year_min'] = int(v)
            else:
                kwargs['year_max'] = int(v)
        # wk_min, wk_max => week_num_min, week_num_max
        if k.lower() in ('wk_min', 'wk_max'):
            del kwargs[k]
            if k.lower() == 'wk_min':
                kwargs['week_num_min'] = int(v)
            else:
                kwargs['week_num_max'] = int(v)
        # yr, year, yrs, years => year_min, year_max
        if k.lower() in ('yr', 'year', 'yrs', 'years'):
            del kwargs[k]
            if isinstance(v, collections.Iterable):
                lst = list(v)
                kwargs['year_min'] = min(lst)
                kwargs['year_max'] = max(lst)
            elif isinstance(v, basestring):
                v = map(int, v.split(','))
                kwargs['year_min'] = min(v)
                kwargs['year_max'] = max(v)
            else:
                kwargs['year_min'] = v
                kwargs['year_max'] = v
        # wk, week, wks, weeks => week_num_min, week_num_max
        if k.lower() in ('wk', 'week', 'wks', 'weeks'):
            del kwargs[k]
            if isinstance(v, collections.Iterable):
                lst = list(v)
                kwargs['week_num_min'] = min(lst)
                kwargs['week_num_max'] = max(lst)
            elif isinstance(v, basestring):
                v = map(int, v.split(','))
                kwargs['week_num_min'] = min(v)
                kwargs['week_num_max'] = max(v)
            else:
                kwargs['week_num_min'] = v
                kwargs['week_num_max'] = v
        # if playoff_round defined, then turn on playoff flag
        if k == 'playoff_round':
            kwargs['game_type'] = 'P'
        if isinstance(v, basestring):
            v = v.split(',')
        if not isinstance(v, collections.Iterable):
            v = [v]

    # reset values to blank for defined kwargs
    for k in kwargs:
        if k in opts:
            opts[k] = []

    # update based on kwargs
    for k, v in kwargs.iteritems():
        # if overwriting a default, overwrite it
        if k in opts:
            # if multiple values separated by commas, split em
            if isinstance(v, basestring):
                v = v.split(',')
            elif not isinstance(v, collections.Iterable):
                v = [v]
            for val in v:
                opts[k].append(val)

    opts['request'] = [1]
    
    qs = '&'.join('{}={}'.format(name, val)
                  for name, vals in sorted(opts.iteritems()) for val in vals)

    return qs

@decorators.switchToDir(os.path.dirname(os.path.realpath(__file__)))
def getInputsOptionsDefaults():
    """Handles scraping options for play finder form.

    :returns: {'name1': {'value': val, 'options': [opt1, ...] }, ... }

    """
    # set time variables
    if os.path.isfile(CONSTANTS_FN):
        modtime = os.path.getmtime(CONSTANTS_FN)
        curtime = time.time()
    else:
        modtime = 0
        curtime = 0
    # if file not found or it's been >= a day, generate new constants
    if not (os.path.isfile(CONSTANTS_FN) and
            int(curtime) - int(modtime) <= 24*60*60):

        # must generate the file
        print 'Regenerating constants file'

        html = utils.getHTML(GAME_PLAY_URL)
        doc = pq(html)
        
        def_dict = {}
        # start with input elements
        for inp in doc('form#play_finder input[name]'):
            name = inp.attrib['name']
            # add blank dict if not present
            if name not in def_dict:
                def_dict[name] = {
                    'value': set(),
                    'options': set(),
                    'type': inp.type
                }

            val = inp.attrib.get('value', '')
            # handle checkboxes and radio buttons
            if inp.type in ('checkbox', 'radio'):
                # deal with default value
                if 'checked' in inp.attrib:
                    def_dict[name]['value'].add(val)
                # add to options
                def_dict[name]['options'].add(val)
            # handle other types of inputs (only other type is hidden?)
            else:
                def_dict[name]['value'].add(val)


        # for dropdowns (select elements)
        for sel in doc('form#play_finder select[name]'):
            name = sel.attrib['name']
            # add blank dict if not present
            if name not in def_dict:
                def_dict[name] = {
                    'value': set(),
                    'options': set(),
                    'type': 'select'
                }
            
            # deal with default value
            defaultOpt = pq(sel)('option[selected]')
            if len(defaultOpt):
                defaultOpt = defaultOpt[0]
                def_dict[name]['value'].add(defaultOpt.attrib.get('value', ''))
            else:
                def_dict[name]['value'].add(
                    pq(sel)('option')[0].attrib.get('value', '')
                )

            # deal with options
            def_dict[name]['options'] = {
                opt.attrib['value'] for opt in pq(sel)('option')
                if opt.attrib.get('value')
            }
        
        # ignore QB kneels by default
        def_dict['include_kneels']['value'] = ['0']

        def_dict.pop('request', None)
        def_dict.pop('use_favorites', None)
        
        with open(CONSTANTS_FN, 'w+') as f:
            for k in def_dict:
                try:
                    def_dict[k]['value'] = sorted(
                        list(def_dict[k]['value']), key=int
                    )
                    def_dict[k]['options'] = sorted(
                        list(def_dict[k]['options']), key=int
                    )
                except:
                    def_dict[k]['value'] = sorted(list(def_dict[k]['value']))
                    def_dict[k]['options'] = sorted(list(def_dict[k]['options']))
            json.dump(def_dict, f)

    # else, just read variable from cached file
    else:
        with open(CONSTANTS_FN, 'r') as const_f:
            def_dict = json.load(const_f)

    return def_dict