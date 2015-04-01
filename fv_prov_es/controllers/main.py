import os, json, requests, types
from datetime import datetime
from flask import Blueprint, render_template, flash, request, redirect, url_for, Response, current_app, jsonify
from flask.ext.login import login_user, logout_user, login_required

from fv_prov_es import cache
from fv_prov_es.forms import LoginForm
from fv_prov_es.models import User
from fv_prov_es.lib.graphviz import add_graphviz_positions
from fv_prov_es.lib.utils import get_prov_es_json, update_dict

main = Blueprint('main', __name__)


@main.route('/')
@cache.cached(timeout=1000)
def home():
    return render_template('facetview.html',
                           title='PROV-ES FacetView',
                           current_year=datetime.now().year)


@main.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        # For demonstration purposes the password in stored insecurely
        user = User.query.filter_by(username=form.username.data,
                                    password=form.password.data).first()

        if user:
            login_user(user)

            flash("Logged in successfully.", "success")
            return redirect(request.args.get("next") or url_for(".home"))
        else:
            flash("Login failed.", "danger")

    return render_template("login.html", form=form)


@main.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "success")

    return redirect(url_for(".home"))


@main.route("/restricted")
@login_required
def restricted():
    return "You can only see this if you are logged in!", 200


@main.route('/fdl', methods=['GET'])
@cache.cached(timeout=1000)
def fdl():
    """Display FDL for a particular job."""

    # get id
    id = request.args.get('id', None)
    if id is None:
        return jsonify({
            'success': False,
            'message': "No id specified."
        }), 500

    return render_template('fdl.html',
                           title='PROV-ES Lineage Graph',
                           id=id,
                           current_year=datetime.now().year)


@cache.cached(timeout=1000)
def parse_d3(pej, show_props=False, show_prop_ids=None):
    """Return d3 node data structure for an activity, entity, or agent."""

    if show_prop_ids is None: show_prop_ids = []

    # viz dict
    nodes = [] 
    input_ents = []
    output_ents = []
    associations = []
    e2e_relations = []
    a2e_relations = []
    viz_dict = {'nodes': [], 'links': []}

    # add agent nodes
    for a in pej.get('agent', {}):
        agent = pej['agent'][a]
        if isinstance(agent['prov:type'], types.DictType):
            prov_type = agent['prov:type']['$']
        else: prov_type = agent['prov:type']
        viz_dict['nodes'].append({
            'id': a,
            'group': 1,
            'size': 1000,
            'shape': 'triangle-down',
            'prov_type': 'agent',
            'doc': agent,
        })
        nodes.append(a)

    # add activities
    for a in pej.get('activity', {}):
        act = pej['activity'][a]
        viz_dict['nodes'].append({
            'id': a,
            'group': 2,
            'size': 3000,
            'shape': 'square',
            'prov_type': 'activity',
            'doc': act,
        })
        nodes.append(a)
        if 'prov:wasAssociatedWith' in act:
            ag = act['prov:wasAssociatedWith']
            if (show_props and a in show_prop_ids) or ag in show_prop_ids:
                if ag in pej.get('agent', {}):
                    agent = pej['agent'][ag]
                else:
                    agent = get_prov_es_json(ag)['_source']['prov_es_json']['agent'][ag]
                if isinstance(agent['prov:type'], types.DictType):
                    prov_type = agent['prov:type']['$']
                else: prov_type = agent['prov:type']
                viz_dict['nodes'].append({
                    'id': ag,
                    'group': 1,
                    'size': 1000,
                    'shape': 'triangle-down',
                    'prov_type': 'agent',
                    'doc': agent,
                })
                nodes.append(ag)
                associations.append({
                    'source': act['prov:wasAssociatedWith'],
                    'target': a,
                    'concept': 'prov:wasAssociatedWith',
                })
        if 'eos:usesSoftware' in act:
            e = act['eos:usesSoftware']
            if (show_props and a in show_prop_ids) or e in show_prop_ids:
                if e in pej.get('entity', {}):
                    ent = pej['entity'][e]
                else:
                    ent = get_prov_es_json(e)['_source']['prov_es_json']['entity'][e]
                    viz_dict['nodes'].append({
                        'id': e,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent,
                    })
                    nodes.append(e)
                a2e_relations.append({
                    'source': a,
                    'target': act['eos:usesSoftware'],
                    'concept': 'eos:usesSoftware',
                })
        
    # add entities
    for e in pej.get('entity', {}):
        ent = pej['entity'][e]
        viz_dict['nodes'].append({
            'id': e,
            'group': 3,
            'size': 1000,
            'prov_type': 'entity',
            'doc': ent,
        })
        nodes.append(e)
        if 'gcis:sourceInstrument' in ent:
            e2 = ent['gcis:sourceInstrument']
            if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                if e2 in pej.get('entity', {}):
                    ent2 = pej['entity'][e2]
                elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                    ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                    viz_dict['nodes'].append({
                        'id': e2,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent2,
                    })
                    nodes.append(e2)
                e2e_relations.append({
                    'source': e,
                    'target': ent['gcis:sourceInstrument'],
                    'concept': 'gcis:sourceInstrument',
                })
        if 'gcis:inInstrument' in ent:
            e2 = ent['gcis:inInstrument']
            if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                if e2 in pej.get('entity', {}):
                    ent2 = pej['entity'][e2]
                elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                    ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                    viz_dict['nodes'].append({
                        'id': e2,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent2,
                    })
                    nodes.append(e2)
                e2e_relations.append({
                    'source': e,
                    'target': ent['gcis:inInstrument'],
                    'concept': 'gcis:inInstrument',
                })
        if 'gcis:hasSensor' in ent:
            e2 = ent['gcis:hasSensor']
            if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                if e2 in pej.get('entity', {}):
                    ent2 = pej['entity'][e2]
                elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                    ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                    viz_dict['nodes'].append({
                        'id': e2,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent2,
                    })
                    nodes.append(e2)
                e2e_relations.append({
                    'source': e,
                    'target': ent['gcis:hasSensor'],
                    'concept': 'gcis:hasSensor',
                })
        if 'gcis:inPlatform' in ent:
            e2 = ent['gcis:inPlatform']
            if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                if e2 in pej.get('entity', {}):
                    ent2 = pej['entity'][e2]
                elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                    ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                    viz_dict['nodes'].append({
                        'id': e2,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent2,
                    })
                    nodes.append(e2)
                e2e_relations.append({
                    'source': ent['gcis:inPlatform'],
                    'target': e,
                    'concept': 'gcis:inPlatform',
                })
        if 'gcis:hasGoverningOrganization' in ent:
            e2 = ent['gcis:hasGoverningOrganization']
            if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                if e2 in pej.get('entity', {}):
                    ent2 = pej['entity'][e2]
                elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                    ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                    viz_dict['nodes'].append({
                        'id': e2,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent2,
                    })
                    nodes.append(e2)
                e2e_relations.append({
                    'source': ent['gcis:hasGoverningOrganization'],
                    'target': e,
                    'concept': 'gcis:hasGoverningOrganization',
                })
        if 'gcis:hasInstrument' in ent:
            e2 = ent['gcis:hasInstrument']
            if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                if e2 in pej.get('entity', {}):
                    ent2 = pej['entity'][e2]
                elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                    ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                    viz_dict['nodes'].append({
                        'id': e2,
                        'group': 3,
                        'size': 1000,
                        'prov_type': 'entity',
                        'doc': ent2,
                    })
                    nodes.append(e2)
                e2e_relations.append({
                    'source': ent['gcis:hasInstrument'],
                    'target': e,
                    'concept': 'gcis:hasInstrument',
                })

    # add used links
    for u in pej.get('used', {}):
        used = pej['used'][u]

        # get activity
        a = used['prov:activity']
        if a in pej.get('activity', {}):
            act = pej['activity'][a]
        else:
            act = get_prov_es_json(a)['_source']['prov_es_json']['activity'][a]
            viz_dict['nodes'].append({
                'id': a,
                'group': 2,
                'size': 3000,
                'shape': 'square',
                'prov_type': 'activity',
                'doc': act,
            })
            nodes.append(a)
            if 'prov:wasAssociatedWith' in act:
                ag = act['prov:wasAssociatedWith']
                if (show_props and a in show_prop_ids) or ag in show_prop_ids:
                    if ag in pej.get('agent', {}):
                        agent = pej['agent'][ag]
                    else:
                        agent = get_prov_es_json(ag)['_source']['prov_es_json']['agent'][ag]
                    if isinstance(agent['prov:type'], types.DictType):
                        prov_type = agent['prov:type']['$']
                    else: prov_type = agent['prov:type']
                    viz_dict['nodes'].append({
                        'id': ag,
                        'group': 1,
                        'size': 1000,
                        'shape': 'triangle-down',
                        'prov_type': 'agent',
                        'doc': agent,
                    })
                    nodes.append(ag)
                    associations.append({
                        'source': act['prov:wasAssociatedWith'],
                        'target': a,
                        'concept': 'prov:wasAssociatedWith',
                    })
            if 'eos:usesSoftware' in act:
                e = act['eos:usesSoftware']
                if (show_props and a in show_prop_ids) or e in show_prop_ids:
                    if e in pej.get('entity', {}):
                        ent = pej['entity'][e]
                    else:
                        ent = get_prov_es_json(e)['_source']['prov_es_json']['entity'][e]
                        viz_dict['nodes'].append({
                            'id': e,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent,
                        })
                        nodes.append(e)
                    a2e_relations.append({
                        'source': a,
                        'target': act['eos:usesSoftware'],
                        'concept': 'eos:usesSoftware',
                    })
        

        # get entity
        e = used['prov:entity']
        if e in pej.get('entity', {}):
            ent = pej['entity'][e]
        else:
            ent = get_prov_es_json(e)['_source']['prov_es_json']['entity'][e]
            viz_dict['nodes'].append({
                'id': e,
                'group': 3,
                'size': 1000,
                'prov_type': 'entity',
                'doc': ent,
            })
            nodes.append(e)
            if 'gcis:sourceInstrument' in ent:
                e2 = ent['gcis:sourceInstrument']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': e,
                        'target': ent['gcis:sourceInstrument'],
                        'concept': 'gcis:sourceInstrument',
                    })
            if 'gcis:inInstrument' in ent:
                e2 = ent['gcis:inInstrument']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': e,
                        'target': ent['gcis:inInstrument'],
                        'concept': 'gcis:inInstrument',
                    })
            if 'gcis:hasSensor' in ent:
                e2 = ent['gcis:hasSensor']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': e,
                        'target': ent['gcis:hasSensor'],
                        'concept': 'gcis:hasSensor'
                    })
            if 'gcis:inPlatform' in ent:
                e2 = ent['gcis:inPlatform']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': ent['gcis:inPlatform'],
                        'target': e,
                        'concept': 'gcis:inPlatform',
                    })
            if 'gcis:hasGoverningOrganization' in ent:
                e2 = ent['gcis:hasGoverningOrganization']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': ent['gcis:hasGoverningOrganization'],
                        'target': e,
                        'concept': 'gcis:hasGoverningOrganization',
                    })
            if 'gcis:hasInstrument' in ent:
                e2 = ent['gcis:hasInstrument']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': ent['gcis:hasInstrument'],
                        'target': e,
                        'concept': 'gcis:hasInstrument',
                    })
        
        viz_dict['links'].append({
            'source': nodes.index(a),
            'target': nodes.index(e),
            'type': 'used',
            'concept': 'prov:used',
            'value': 1,
            'doc': used,
        })
        input_ents.append(e)
        
    # add generated links
    for g in pej.get('wasGeneratedBy', {}):
        gen = pej['wasGeneratedBy'][g]

        # get activity
        a = gen['prov:activity']
        if a in pej.get('activity', {}):
            act = pej['activity'][a]
        else:
            act = get_prov_es_json(a)['_source']['prov_es_json']['activity'][a]
            viz_dict['nodes'].append({
                'id': a,
                'group': 2,
                'size': 3000,
                'shape': 'square',
                'prov_type': 'activity',
                'doc': act,
            })
            nodes.append(a)
            if 'prov:wasAssociatedWith' in act:
                ag = act['prov:wasAssociatedWith']
                if (show_props and a in show_prop_ids) or ag in show_prop_ids:
                    if ag in pej.get('agent', {}):
                        agent = pej['agent'][ag]
                    else:
                        agent = get_prov_es_json(ag)['_source']['prov_es_json']['agent'][ag]
                    if isinstance(agent['prov:type'], types.DictType):
                        prov_type = agent['prov:type']['$']
                    else: prov_type = agent['prov:type']
                    viz_dict['nodes'].append({
                        'id': ag,
                        'group': 1,
                        'size': 1000,
                        'shape': 'triangle-down',
                        'prov_type': 'agent',
                        'doc': agent,
                    })
                    nodes.append(ag)
                    associations.append({
                        'source': act['prov:wasAssociatedWith'],
                        'target': a,
                        'concept': 'prov:wasAssociatedWith',
                    })
            if 'eos:usesSoftware' in act:
                e = act['eos:usesSoftware']
                if (show_props and a in show_prop_ids) or e in show_prop_ids:
                    if e in pej.get('entity', {}):
                        ent = pej['entity'][e]
                    else:
                        ent = get_prov_es_json(e)['_source']['prov_es_json']['entity'][e]
                        viz_dict['nodes'].append({
                            'id': e,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent,
                        })
                        nodes.append(e)
                    a2e_relations.append({
                        'source': a,
                        'target': act['eos:usesSoftware'],
                        'concept': 'eos:usesSoftware',
                    })
        
        # get entity
        e = gen['prov:entity']
        if e in pej.get('entity', {}):
            ent = pej['entity'][e]
        else:
            ent = get_prov_es_json(e)['_source']['prov_es_json']['entity'][e]
            viz_dict['nodes'].append({
                'id': e,
                'group': 3,
                'size': 1000,
                'prov_type': 'entity',
                'doc': ent,
            })
            nodes.append(e)
            if 'gcis:sourceInstrument' in ent:
                e2 = ent['gcis:sourceInstrument']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': e,
                        'target': ent['gcis:sourceInstrument'],
                        'concept': 'gcis:sourceInstrument',
                    })
            if 'gcis:inInstrument' in ent:
                e2 = ent['gcis:inInstrument']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': e, 
                        'target': ent['gcis:inInstrument'],
                        'concept': 'gcis:inInstrument',
                    })
            if 'gcis:hasSensor' in ent:
                e2 = ent['gcis:hasSensor']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': e,
                        'target': ent['gcis:hasSensor'],
                        'concept': 'gcis:hasSensor',
                    })
            if 'gcis:inPlatform' in ent:
                e2 = ent['gcis:inPlatform']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': ent['gcis:inPlatform'],
                        'target': e,
                        'concept': 'gcis:inPlatform',
                    })
            if 'gcis:hasGoverningOrganization' in ent:
                e2 = ent['gcis:hasGoverningOrganization']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': ent['gcis:hasGoverningOrganization'],
                        'target': e,
                        'concept': 'gcis:hasGoverningOrganization',
                    })
            if 'gcis:hasInstrument' in ent:
                e2 = ent['gcis:hasInstrument']
                if (show_props and e in show_prop_ids) or e2 in show_prop_ids:
                    if e2 in pej.get('entity', {}):
                        ent2 = pej['entity'][e2]
                    elif e2 in get_prov_es_json(e2)['_source']['prov_es_json'].get('entity', {}):
                        ent2 = get_prov_es_json(e2)['_source']['prov_es_json']['entity'][e2]
                        viz_dict['nodes'].append({
                            'id': e2,
                            'group': 3,
                            'size': 1000,
                            'prov_type': 'entity',
                            'doc': ent2,
                        })
                        nodes.append(e2)
                    e2e_relations.append({
                        'source': ent['gcis:hasInstrument'],
                        'target': e,
                        'concept': 'gcis:hasInstrument',
                    })
        
        viz_dict['links'].append({
            'source': nodes.index(e),
            'target': nodes.index(a),
            'type': 'wasGeneratedBy',
            'concept': 'prov:wasGeneratedBy',
            'value': 1,
            'doc': gen,
        })
        output_ents.append(e)
        
    # add hadMember links
    for h in pej.get('hadMember', {}):
        hm = pej['hadMember'][h]

        # get collection
        c = hm['prov:collection']
        if c in pej.get('entity', {}):
            col = pej['entity'][c]
        else:
            col = get_prov_es_json(c)['_source']['prov_es_json']['entity'][c]
            viz_dict['nodes'].append({
                'id': c,
                'group': 3,
                'size': 1000,
                'prov_type': 'entity',
                'doc': col,
            })
            nodes.append(c)
        
        # get entity
        e = hm['prov:entity']
        if e in pej.get('entity', {}):
            ent = pej['entity'][e]
        else:
            ent = get_prov_es_json(e)['_source']['prov_es_json']['entity'][e]
            viz_dict['nodes'].append({
                'id': e,
                'group': 3,
                'size': 1000,
                'prov_type': 'entity',
                'doc': ent,
            })
            nodes.append(e)
        
        e2e_relations.append({
            'source': c,
            'target': e,
            'concept': hm.get('prov:type', 'prov:hadMember'),
            'doc': hm,
        })

    # modify color of entities that are inputs and outputs or just outputs
    new_nodes = []
    for n in viz_dict['nodes']:
        if n['id'] in input_ents and n['id'] in output_ents:
            n['group'] = 6
        elif n['id'] in output_ents:
            n['group'] = 5
        elif n['id'] in input_ents:
            n['group'] = 4
        new_nodes.append(n)
    viz_dict['nodes'] = new_nodes
    
    # add association links
    asc_dict = {}
    for a in associations:
        asc = "%s_%s" % (a['source'], a['target'])
        if asc in asc_dict: continue
        viz_dict['links'].append({
            'source': nodes.index(a['source']),
            'target': nodes.index(a['target']),
            'type': 'associated',
            'concept': 'prov:wasAssociatedWith',
            'value': 1,
            'doc': a.get('doc', None),
        })
        asc_dict[asc] = True

    # add e2e_relations links
    e2e_rel_dict = {}
    for r in e2e_relations:
        rel = "%s_%s" % (r['source'], r['target'])
        if rel in e2e_rel_dict: continue
        if r['source'] not in nodes or r['target'] not in nodes: continue
        viz_dict['links'].append({
            'source': nodes.index(r['source']),
            'target': nodes.index(r['target']),
            'type': 'e2e_related',
            'concept': r['concept'],
            'value': 1,
            'doc': r.get('doc', None),
        })
        e2e_rel_dict[rel] = True

    # add a2e_relations links
    a2e_rel_dict = {}
    for r in a2e_relations:
        rel = "%s_%s" % (r['source'], r['target'])
        if rel in a2e_rel_dict: continue
        if r['source'] not in nodes or r['target'] not in nodes: continue
        viz_dict['links'].append({
            'source': nodes.index(r['source']),
            'target': nodes.index(r['target']),
            'type': 'a2e_related',
            'concept': r['concept'],
            'value': 1,
            'doc': r.get('doc', None),
        })
        a2e_rel_dict[rel] = True

    #current_app.logger.debug("viz_dict: %s" % json.dumps(viz_dict, indent=2))
    return viz_dict
       

@main.route('/fdl/data', methods=['GET'])
@cache.cached(timeout=1000)
def fdl_data():
    """Get FDL data for visualization."""

    # get id
    id = request.args.get('id', None)
    if id is None:
        return jsonify({
            'success': False,
            'message': "No id specified."
        }), 500
    if request.args.get('lineage', 'false').lower() == 'true':
        lineage = True
    else: lineage = False
    if request.args.get('show_props', 'false').lower() == 'true':
        show_props = True
    else: show_props = False

    # do lineage?
    if lineage is False:
        viz_dict = parse_d3(get_prov_es_json(id)['_source']['prov_es_json'], show_props)
    else:
        es_url = current_app.config['ES_URL']
        es_index = current_app.config['PROVES_ES_ALIAS']
        query = { 'query': { 'query_string': { 'query': '"%s"' % id } } }
        #current_app.logger.debug("ES query for query(): %s" % json.dumps(query, indent=2))
        r = requests.post('%s/%s/_search?search_type=scan&scroll=60m&size=100' %
                          (es_url, es_index), data=json.dumps(query))
        scan_result = r.json()
        if r.status_code != 200:
            current_app.logger.debug("Failed to query ES. Got status code %d:\n%s" %
                                     (r.status_code, json.dumps(scan_result, indent=2)))
        r.raise_for_status()

        # get results
        results = []
        scroll_id = scan_result['_scroll_id']
        while True:
            r = requests.post('%s/_search/scroll?scroll=10m' % es_url, data=scroll_id)
            res = r.json()
            scroll_id = res['_scroll_id']
            if len(res['hits']['hits']) == 0: break
            results.extend(res['hits']['hits'])

            # break at 100 results or else FDL gets overwhelmed
            if len(results) > 100: break

        #current_app.logger.debug("result: %s" % pformat(r.json()))
        merged_doc = {}
        for d in results:
            merged_doc = update_dict(merged_doc, d['_source']['prov_es_json'])
        #current_app.logger.debug("merged_doc: %s" % json.dumps(merged_doc, indent=2))
        viz_dict = parse_d3(merged_doc, show_props=show_props, show_prop_ids=[id])

    #current_app.logger.debug("fdl_data viz_dict: %s" % json.dumps(viz_dict, indent=2))
    return jsonify(viz_dict)


@main.route('/fdl/data/layout', methods=['POST'])
@cache.cached(timeout=1000)
def layout():
    """Return graphviz locations for FDL data for visualization."""

    # get viz dict
    viz_dict = request.form.get('viz_dict', None)
    if viz_dict is None:
        return jsonify({
            'success': False,
            'message': "No viz_dict specified."
        }), 500
    viz_dict = json.loads(viz_dict)

    # add graphviz position
    viz_dict = add_graphviz_positions(viz_dict)

    return jsonify(viz_dict)


@main.route('/search_bundle', methods=['GET'])
@cache.cached(timeout=1000)
def search_bundle():
    """Redirect to faceted view of all docs related to a doc."""

    # get viz dict
    id = request.args.get('id', None)
    if id is None:
        return jsonify({
            'success': False,
            'message': "No id specified."
        }), 500

    # query
    query = {
        "query": {
            "query_string": {
                "query": '"%s"' % id
            }
        }
    }
    return redirect(url_for(".home", source=json.dumps(query)))
