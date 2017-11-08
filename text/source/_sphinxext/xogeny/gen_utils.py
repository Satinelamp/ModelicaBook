import re
import os
import sys
import json
from jinja2 import PackageLoader, Environment

path = os.path.abspath(os.path.join(__file__,"..","..","..","..",".."));

print "Path: "+str(path)

results = {}
plots = {}

def findModel(*frags):
    rfrags = map(lambda x: re.compile(x), frags)
    res = []
    root = os.path.join(path, "ModelicaByExample")
    for ent in os.walk(root):
        for f in ent[2]:
            if f=="package.mo":
                continue
            match = True
            full = os.path.join(ent[0], f)
            rel = full[(len(path)+1):]
            if rel[-3:]!=".mo":
                continue
            modname = rel[:-3].replace("/",".")
            for rfrag in rfrags:
                if len(rfrag.findall(modname))==0:
                    match = False
            if match:
                entry = (full, rel, modname)
                res.append(entry)
    if len(res)==1:
        return res[0]
    else:
        print "Unable to find a unique match for "+str(frags)+" matches include:"
        for r in res:
            print str(r)
        sys.exit(1)

def add_case(frags, res, stopTime=None, tol=1e-3, ncp=500, mods={},
             msl=False, ms=False, compfails=False, simfails=False):
    mod = findModel(*frags)
    if res in results:
        raise NameError("Result %s already exists!" % (res,))
    data = {
        "name": mod[2],
        "path": mod[0],
        "directory": os.path.dirname(mod[0]),
        "stopTime": stopTime,
        "tol": tol,
        "ncp": ncp,
        "mods": mods,
        "msl": msl,
        "ms": ms,
        "compfails": compfails,
        "simfails": simfails
    };
    results[res] = data

class Var(object):
    def __init__(self, name, scale=1.0, legend=None, style="-"):
        self.name = name
        self.style = style
        self.scale = scale
        if legend==None:
            self.legend = name
        else:
            self.legend = legend
    def dict(self):
        return {"name": self.name, "scale": self.scale,
                "legend": self.legend, "style": self.style}
    def __repr__(self):
        return repr(self.dict())

simple_plot_tmpl = """
# Autogenerated script to plot named %s using results: %s
# Generated from the simple_plot_tmpl variable in gen_utils.py
from xogeny.plot_utils import render_simple_plot
import matplotlib

matplotlib.pyplot.rcParams['agg.path.chunksize'] = 20000

render_simple_plot(name=%s, vars=%s, title=%s, legloc=%s, ylabel=%s, ncols=%s, ymin=%s, ymax=%s)
""";

comp_plot_tmpl = """
# Autogenerated script to plot results for model %s
# Generated from the comp_plot_tmpl variable in gen_utils.py
from xogeny.plot_utils import render_comp_plot
render_comp_plot(%s, %s, %s, %s, title=%s, legloc=%s, ylabel=%s)
""";

def add_simple_plot(plot, vars, title, legloc="upper right", ylabel="",
                    res=None, ncols=1, ymin=None, ymax=None):
    if plot in plots:
        raise NameError("Plot named "+plot+" already exists");
    if res==None:
        res = plot
    if not res in results:
        raise NameError("Unable to find result "+res+" for plot "+plot)
    r = results[res]

    plots[plot] = {
        "type": "simple",
        "vars": vars,
        "title": title,
        "legloc": legloc,
        "ylabel": ylabel,
        "ncols": ncols,
        "ymax": ymax,
        "ymin": ymin,
        "res": res
    };

def add_compare_plot(plot, res1, v1, res2, v2, title, legloc="lower right", ylabel=""):
    if plot in plots:
        raise NameError("Plot "+plot+" already exists")
    if not res1 in results:
        raise NameError("Unable to find result "+res1+" in plot "+plot)
    if not res2 in results:
        raise NameError("Unable to find result "+res2+" in plot "+plot)

    plots[plot] = {
        "type": "compare",
        "res1": res1,
        "v1": v1,
        "res2": res2,
        "v2": v2,
        "title": title,
        "legloc": legloc,
        "ylabel": ylabel
    };

def _generate_casedata():
    for plot in plots:
        pdata = plots[plot]
        if pdata["type"]=="simple":
            with open(os.path.join(path, "text", "results",
                               "json", plot+"-case.json"), "w+") as ofp:
                res = results[pdata["res"]]
                obj = dict(pdata)
                obj["vars"] = map(lambda x: x.dict(), pdata["vars"])
                obj["stopTime"] = res["stopTime"]
                obj["ncp"] = res["ncp"]
                obj["tol"] = res["tol"]
                obj["mods"] = res["mods"]
                json.dump(obj, ofp, indent=2)

def _generate_plots():
    for plot in plots:
        pdata = plots[plot]
        with open(os.path.join(path, "text", "plots", plot+".py"), "w+") as ofp:
            if pdata["type"]=="simple":
                ofp.write(simple_plot_tmpl % (repr(plot), repr(pdata["res"]),
                                              repr(pdata["res"]),
                                              repr(pdata["vars"]), repr(pdata["title"]),
                                              repr(pdata["legloc"]), repr(pdata["ylabel"]),
                                              repr(pdata["ncols"]),
                                              repr(pdata["ymin"]), repr(pdata["ymax"])))
            elif pdata["type"]=="compare":
                ofp.write(comp_plot_tmpl % (repr(plot),
                                            repr(pdata["res1"]), repr(pdata["v1"]),
                                            repr(pdata["res2"]), repr(pdata["v2"]),
                                            repr(pdata["title"]),
                                            repr(pdata["legloc"]), repr(pdata["ylabel"])))
            else:
                raise ValueError("Unknown plot type: "+str(pdata["type"]))

script_tmpl = """
setModelicaPath(getModelicaPath()+":"+"%s");
cf := loadModel(ModelicaByExample);
compfails := %s;
getErrorString();

if not compfails and cf==false then
  exit(1);
end if;
    
rec := %s;
getErrorString();
rfile := rec.resultFile;
simfails := %s;

if not simfails and rfile == "" then
  exit(1);
else
  exit(0);
end if;
"""

def _simcmd(model_name, fileNamePrefix, outputFormat="mat", simflags=None,
            stopTime=None, tolerance=None, numberOfIntervals=None):
    ret = """simulate(%s, """ % (model_name,)
    if stopTime:
        ret = ret + """stopTime=%g, """ % (stopTime,)
    if tolerance:
        ret = ret + """tolerance=%g, """ % (tolerance,)
    if numberOfIntervals:
        ret = ret + """numberOfIntervals=%d, """ % (numberOfIntervals,)
    if simflags:
        ret = ret + """simflags="%s", """ % (simflags,)
    ret = ret + """method="dassl","""
    ret = ret + """fileNamePrefix="%s", """ % (fileNamePrefix,)
    ret = ret + """outputFormat="%s")""" % (outputFormat,)
    return ret

def _generate_makefile():
    loader = PackageLoader('xogeny')
    env = Environment(loader=loader)
    genres = env.get_template("gen_result.mos")
    genjs = env.get_template("gen_js.mos")
    genmk = env.get_template("gen.makefile")

    # Generate Makefile
    with open(os.path.join(path, "text", "results", "Makefile"), "w+") as ofp:
        ofp.write(genmk.render({"results": results}))
            
    for res in results:
        data = results[res]
        mods = data["mods"]
        directory = data["directory"]
        srcpath = data["path"]
        if len(mods)==0:
            simflags = "-cpu -ignoreHideResult -emit_protected"
        else:
            simflags = "-cpu -ignoreHideResult -emit_protected -override "+(",".join(map(lambda x: str(x)+"="+str(mods[x]), mods)))

        simfails = "true" if data["simfails"] else "false"
        compfails = "true" if data["compfails"] else "false"
        simcmd = _simcmd(model_name=data["name"], fileNamePrefix=res,
                         simflags=simflags, stopTime=data["stopTime"],
                         tolerance=data["tol"],
                         numberOfIntervals=data["ncp"])
        context = {"path": path, "compfails": compfails,
                   "simcmd": simcmd, "simfails": simfails,
                   "name": data["name"], "pre": res}

        # Write out script to generate simulation results

        with open(os.path.join(path, "text", "results", res+".mos"), "w+") as sfp:
            sfp.write(genres.render(**context));
        # Write out script to generate JavaScript
        with open(os.path.join(path, "text", "results", res+"-js.mos"), "w+") as sfp:
            sfp.write(genjs.render(**context));

def generate():
    _generate_plots()
    _generate_makefile()
    _generate_casedata()
