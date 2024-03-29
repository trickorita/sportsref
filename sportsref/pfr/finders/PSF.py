import collections
import json
import os
import time

from pyquery import PyQuery as pq
import requests

import sportsref

PLAYER_SEASON_URL = ('http://www.pro-football-reference.com/'
                     'play-index/psl_finder.cgi')

CONSTANTS_FN = 'PSFConstants.json'

def PlayerSeasonFinder(**kwargs):
    """ Docstring will be filled in by __init__.py """
    
    if 'offset' not in kwargs:
        kwargs['offset'] = 0

    playerseasons = []
    while True:
        querystring = kwArgsToQS(**kwargs)
        url = '{}?{}'.format(PLAYER_SEASON_URL, querystring)
        if kwargs.get('verbose', False):
            print url
        html = sportsref.utils.getHTML(url)
        doc = pq(html)
        table = doc('table#stats')
        yearTh = table('thead tr[class=""] th[data-stat="year_id"]')[0]
        yearIdx = table('thead tr[class=""] th').index(yearTh)
        for row in table('tbody tr[class=""]').items():
            relURL = row('a[href*="/players/"]').attr.href
            playerID = sportsref.utils.relURLToID(relURL)
            year = int(row('td')[yearIdx].text)
            playerseasons.append((playerID, year))

        if doc('*:contains("Next page")'):
            kwargs['offset'] += 100
        else:
            break

    return playerseasons

def kwArgsToQS(**kwargs):
    """Converts kwargs given to PSF to a querystring.

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
        # bool => 'Y'|'N'
        if isinstance(v, bool):
            kwargs[k] = 'Y' if v else 'N'
        # tm, team => team_id
        if k.lower() in ('tm', 'team'):
            del kwargs[k]
            kwargs['team_id'] = v
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
        # pos, position, positions => pos_is_X
        if k.lower() in ('pos', 'position', 'positions'):
            del kwargs[k]
            # make sure value is list, splitting strings on commas
            if isinstance(v, basestring):
                v = v.split(',')
            if not isinstance(v, collections.Iterable):
                v = [v]
            for pos in v:
                kwargs['pos_is_' + pos] = 'Y'
        # draft_pos, ... => draft_pos_is_X
        if k.lower() in ('draftpos', 'draftposition', 'draftpositions',
                         'draft_pos', 'draft_position', 'draft_positions'):
            del kwargs[k]
            # make sure value is list, splitting strings on commas
            if isinstance(v, basestring):
                v = v.split(',')
            if not isinstance(v, collections.Iterable):
                v = [v]
            for pos in v:
                kwargs['draft_pos_is_' + pos] = 'Y'

    # reset opts values to blank for defined kwargs
    for k in kwargs:
        # for regular keys
        if k in opts:
            opts[k] = []
        # for positions
        if k.startswith('pos_is'):
            # if a position is defined, mark all pos as 'N'
            for k in opts:
                if k.startswith('pos_is'):
                    opts[k] = ['N']
        # for draft positions
        if k.startswith('draft_pos_is'):
            # if a draft draft_position is defined, mark all draft draft_pos as 'N'
            for k in opts:
                if k.startswith('draft_pos_is'):
                    opts[k] = ['N']

    # update based on kwargs
    for k, v in kwargs.iteritems():
        # if overwriting a default, overwrite it (with a list so the
        # opts -> querystring list comp works)
        if k in opts:
            # if multiple values separated by commas, split em
            if isinstance(v, basestring):
                v = v.split(',')
            # otherwise, make sure it's a list
            elif not isinstance(v, collections.Iterable):
                v = [v]
            # then, add all values to the querystring dict (opts)
            for val in v:
                opts[k].append(val)
            # now, for Y|N inputs, make sure there's only one entry
            # (if any entries are Y, then the entry becomes Y)
            if all([val in ('Y', 'y', 'N', 'n') for val in opts[k]]):
                opts[k] = ('Y' if any([val in ('Y', 'y') for val in opts[k]])
                           else 'N')

    opts['request'] = [1]
    opts['offset'] = [kwargs.get('offset', 0)]

    qs = '&'.join('{}={}'.format(name, val)
                  for name, vals in sorted(opts.iteritems()) for val in vals)

    return qs

@sportsref.decorators.switchToDir(os.path.dirname(os.path.realpath(__file__)))
def getInputsOptionsDefaults():
    """Handles scraping options for player-season finder form.

    :returns: {'name1': {'value': val, 'options': [opt1, ...] }, ... }
    """
    # set time variables
    if os.path.isfile(CONSTANTS_FN):
        modtime = int(os.path.getmtime(CONSTANTS_FN))
        curtime = int(time.time())
    # if file found and it's been <= a week
    if os.path.isfile(CONSTANTS_FN) and curtime - modtime <= 7*24*60*60:

        # just read the dict from cached file
        with open(CONSTANTS_FN, 'r') as const_f:
            def_dict = json.load(const_f)

    # otherwise, we must regenerate the dict and rewrite it
    else:

        print 'Regenerating PSFConstants file'

        html = sportsref.utils.getHTML(PLAYER_SEASON_URL)
        doc = pq(html)

        def_dict = {}
        # start with input elements
        for inp in doc('form#psl_finder input[name]'):
            name = inp.attrib['name']
            # add blank dict if not present
            if name not in def_dict:
                def_dict[name] = {
                    'value': set(),
                    'options': set(),
                    'type': inp.attrib['type']
                }

            # handle checkboxes and radio buttons
            if inp.attrib['type'] in ('checkbox', 'radio'):
                # deal with default value
                if 'checked' in inp.attrib:
                    def_dict[name]['value'].add(inp.attrib['value'])
                # add to options
                def_dict[name]['options'].add(inp.attrib['value'])
            # handle other types of inputs (only other type is hidden?)
            else:
                def_dict[name]['value'].add(inp.attrib.get('value', ''))

        # deal with dropdowns (select elements)
        for sel in doc.items('form#psl_finder select[name]'):
            name = sel.attr['name']
            # add blank dict if not present
            if name not in def_dict:
                def_dict[name] = {
                    'value': set(),
                    'options': set(),
                    'type': 'select'
                }

            # deal with default value
            defaultOpt = sel('option[selected]')
            if len(defaultOpt):
                defaultOpt = defaultOpt[0]
                def_dict[name]['value'].add(defaultOpt.attrib.get('value', ''))
            else:
                def_dict[name]['value'].add(
                    sel('option')[0].attrib.get('value', '')
                )
                
            # deal with options
            def_dict[name]['options'] = {
                opt.attrib['value'] for opt in sel('option')
                if opt.attrib.get('value')
            }

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
    
    return def_dict
