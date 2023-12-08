import pandas as pd
from gurobipy import *
from data.constants import *


# ------------ Decision Variables -----------------

# ----------initialize decision_vars ----------------------

opt_mod = Model(name="scenario1")
# For each retailer, create binary decision variable for whether or not we should ship to them
# linear cost if dec_var == 1, 50000 if dec_var == 0

retailer_decision_vars = []
# retailer_decision_vars is a list of dicts: {var: GRB.var, LocationID, Position, Role, NodeID}
for i in RETAILER:
    varname = i["LocationID"]
    a = opt_mod.addVar(name=varname, vtype=BINARY)
    copy = i.copy()
    copy["var"] = a
    retailer_decision_vars.append(copy)
# 18.11 adding retailer_decision_vars successful, tested


# --- initialize decision_vars ----------------------

decision_vars_attributes = ["var", "part", "start", "dest", "mode"]
decision_vars = []


# 16.11: update this part of code to match new format of decision_vars

# decision_vars: list of dicts, one dict correspond to one decision variable. Each decision variable has a GRB.var, part of supply chain (x,y,z), start node, destination node, transport mode, timeBucketstart, timeBucketEnd.
# start node id and destination node id as index


# DC to retailers
# attempt using ID as index
for dc in DC:
    for retailer in RETAILER:
        for k in co2cost.keys():
            varname = (
                "x" + k + str(dc["LocationID"]) + "-" + str(retailer["LocationID"])
            )
            a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

            var_entry = {
                "var": a,
                "part": "x",  # x = DC to retailer in supply chain
                "start": dc["LocationID"],
                "dest": retailer["LocationID"],
                "mode": k,
            }
            decision_vars.append(var_entry)


for cd in CD:
    for dc in DC:
        for k in co2cost.keys():
            varname = "y" + k + str(cd["LocationID"]) + "-" + str(dc["LocationID"])
            a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

            var_entry = {
                "var": a,
                "part": "y",  # y = CD to DC in supply chain
                "start": cd["LocationID"],
                "dest": dc["LocationID"],
                "mode": k,
            }
            decision_vars.append(var_entry)


for source in SOURCE:
    for cd in CD:
        for k in co2cost.keys():
            if k == "road":
                continue
            varname = "z" + k + str(source["LocationID"]) + "-" + str(cd["LocationID"])
            a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

            var_entry = {
                "var": a,
                "part": "z",  # z = source to CD in supply chain
                "start": source["LocationID"],
                "dest": cd["LocationID"],
                "mode": k,
            }
            decision_vars.append(var_entry)


# objective function: minimize sum
minCosts = sum(
    j["var"]
    * (
        get_distance(distance_data, j["start"], j["dest"])
        * (transportcost["air"] + slowcost["air"])
        + locationCosts[j["part"]][j["start"]]
    )
    for j in decision_vars
)
obj_func = minCosts

opt_mod.setObjective(obj_func, GRB.MINIMIZE)

# --- set objective function


# --- add constraints -------


# DC capacity is met


# imaginary constraints
# c1 = opt_mod.addConstr(i["var"] >= 1 for i in retailer_decision_vars)
# c2 = opt_mod.addConstr(decision_vars["y"]["road"][0] + decision_vars["z"]["air"][0] >= 3 )

# 18.11 test if addConstr works on retailer_decision_vars
for i in retailer_decision_vars:
    opt_mod.addConstr(i["var"] >= 0)

for j in decision_vars:
    opt_mod.addConstr(j["var"] >= 0)


# 20.11 2023 add constraint for each retailer: sum of amount sent to one retailer = demand of that retailer
for retailer in demands:
    opt_mod.addConstr(
        sum(
            list(
                j["var"]
                for j in decision_vars
                if j["part"] == "x" and j["dest"] == retailer
            )
        )
        == demands[retailer]
    )


for dc in DC:
    # amount to send out from this dc
    amount_dc = sum(
        list(
            j["var"]
            for j in decision_vars
            if j["part"] == "x" and j["start"] == dc["LocationID"]
        )
    )
    opt_mod.addConstr(amount_dc <= DC_constraints[dc["LocationID"]])
    opt_mod.addConstr(
        sum(
            list(
                j["var"]
                for j in decision_vars
                if j["part"] == "y" and j["dest"] == dc["LocationID"]
            )
        )
        == amount_dc
    )

for cd in CD:
    # amount to send out from this cd
    amount_cd = sum(
        j["var"]
        for j in decision_vars
        if j["part"] == "y" and j["start"] == cd["LocationID"]
    )
    opt_mod.addConstr(
        sum(
            j["var"]
            for j in decision_vars
            if j["part"] == "z" and j["dest"] == cd["LocationID"]
        )
        == amount_cd
    )

opt_mod.optimize()


print("Objective Function Value: %f" % opt_mod.objVal)
current_optimum = opt_mod.objVal

for v in opt_mod.getVars():
    if (
        v.varName.startswith("x")
        or v.varName.startswith("y")
        or v.varName.startswith("z")
    ):
        if v.x != 0:
            print("%s: %g" % (v.varName, v.x))
    else:
        continue


totalCost = 0
for v in decision_vars:
    if v["part"] == "x":
        DC_amount[v["start"]] += v["var"].x
    elif v["part"] == "y":
        CD_amount[v["start"]] += v["var"].x
    else:
        SOURCE_amount[v["start"]] += v["var"].x

    dist = get_distance(distance_data, v["start"], v["dest"])
    totalCost += v["var"].x * slowcost["air"] * dist
    totalCost += v["var"].x * transportcost["air"] * dist
    totalCost += v["var"].x * locationCosts[v["part"]][v["start"]]
totalCost = format(totalCost, "_")


totalEmission = 0
for v in decision_vars:
    dist = get_distance(distance_data, v["start"], v["dest"])
    totalEmission += v["var"].x * co2cost[v["mode"]] * dist
totalEmission = format(totalEmission, "_")


print(f"current optimum: {current_optimum}")
print(f"Total CO2 emission of all units: {totalEmission} kg")
print(f"Total cost: {totalCost} chf")
print(
    "Total cost here contains slowness cost, transportation cost sourcing costs and handling cost"
)


# ----- calculate monetary cost ---------------------
