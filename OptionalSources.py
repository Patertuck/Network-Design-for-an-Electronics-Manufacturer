import pandas as pd
from gurobipy import *
from data.constants import *

opt_mod = Model(name="OptionalSources")
# ------------ Decision Variables -----------------

# --- initialize decision_vars ----------------------


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
        varname = "x" + str(dc["LocationID"]) + "-" + str(retailer["LocationID"])
        a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

        var_entry = {
            "var": a,
            "part": "x",  # x = DC to retailer in supply chain
            "start": dc["LocationID"],
            "dest": retailer["LocationID"],
        }
        decision_vars.append(var_entry)


for cd in CD:
    for dc in DC:
        varname = "y" + str(cd["LocationID"]) + "-" + str(dc["LocationID"])
        a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

        var_entry = {
            "var": a,
            "part": "y",  # y = CD to DC in supply chain
            "start": cd["LocationID"],
            "dest": dc["LocationID"],
        }
        decision_vars.append(var_entry)


for source in SOURCE:
    for cd in CD:
        varname = "z" + str(source["LocationID"]) + "-" + str(cd["LocationID"])
        a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

        var_entry = {
            "var": a,
            "part": "z",  # z = source to CD in supply chain
            "start": source["LocationID"],
            "dest": cd["LocationID"],
        }
        decision_vars.append(var_entry)

big_M = 10000000000

for optionalSource in OPTIONALSOURCE:
    for dc in DC:
        varname = "o" + str(optionalSource["LocationID"]) + "-" + str(dc["LocationID"])
        a = opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)
        varname_build = varname + "_build"
        build = opt_mod.addVar(name=varname_build, vtype=BINARY)

        opt_mod.addConstr(a >= 0)  # Ensure a is non-negative

        # Constraint to link a and build with big M
        opt_mod.addConstr(a <= big_M * build)

        var_entry = {
            "var": a,
            "part": "o",  # x = DC to retailer in the supply chain
            "start": optionalSource["LocationID"],
            "dest": dc["LocationID"],
            "build": build
        }
        decision_vars.append(var_entry)


# --------------- working up to here on 18.11

# --- objective function ----------------
# Remember to multiply with kilometers later 16.11.2023 and adjust decision_vars
# 18.11 Remeber to consider retailer decision variables
# obj_junc = sum of all product of (unit transported * cost per unit) in section DC-Retailer

# works: obj_func = sum(i["var"] for i in retailer_decision_vars) + sum(j["var"] for j in decision_vars)


# 18.11 works
# objective function: minimize sum of costs to send from DC to Retailer with cost 2 per unit to send and 50000 to violate contract
# obj_func = sum(list((1-i["var"])*j["var"]*2 + i["var"]*50000 for j in decision_vars for i in retailer_decision_vars))


# 20.11
# objective function: minimize sum of co2 emission to send from DC to Retailer with cost (distance*co2cost) per unit
optionalCost = sum(1250000 * var_entry["build"] for var_entry in decision_vars if var_entry["part"] == "o")


obj_func = (sum(
    j["var"] * distance_entry["distance"] * transportcost["air"]
    for j in decision_vars
    for distance_entry in distance_data
    if distance_entry["start"] == j["start"] and distance_entry["end"] == j["dest"]
) + sum(
    l["var"] * variablecost[l["start"]]
    for l in decision_vars
    if l["part"] == "o"
) + optionalCost + sum(list(j["var"] * sourcingcost[j["start"]]
       for j in decision_vars if j["part"] == 'z'
       for distance_entry in distance_data if distance_entry["start"] == j["start"]
       and distance_entry["end"] == j["dest"])))




""" obj_func = sum([item["var"] * co2cost[mode] for item in decision_vars["x"][mode] for mode in co2cost.keys()]) + sum([item["var"] * co2cost[mode] for item in decision_vars["y"][mode] for mode in co2cost.keys()]) + sum([item["var"] * co2cost[mode] for item in decision_vars["z"][mode] for mode in co2cost.keys()]) """

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


# 20.11.2023 add constraints for each DC: No DC sends out more than its capacity

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
                or j["part"] == "o" and j["dest"] == dc["LocationID"]
            )
        )
        == amount_dc
    )

for cd in CD:
    # amount to send out from this cd
    amount_cd = sum(
        list(
            j["var"]
            for j in decision_vars
            if j["part"] == "y" and j["start"] == cd["LocationID"]
        )
    )
    opt_mod.addConstr(
        sum(
            list(
                j["var"]
                for j in decision_vars
                if j["part"] == "z" and j["dest"] == cd["LocationID"]
            )
        )
        == amount_cd
    )

"""   
for source in CD:
    amount_source = sum(list(j["var"] for j in decision_vars if j["part"] == 'z' and j["start"] == source["LocationID"])) 
    opt_mod.addConstr(sum(list(j["var"] for j in decision_vars if j["part"] == 'z' and j["dest"] == dc["LocationID"])) == amount_cd)
"""


# --- constraints -----------------------------


# check if we ship to each retailer: addconstr(costtoretailer <= 50000)


# ----- constraints --------------------------------

opt_mod.optimize()

print("Objective Function Value: %f" % opt_mod.objVal)
current_optimum = opt_mod.objVal
total_cost = 0

for v in opt_mod.getVars():
    if (
        v.varName.startswith("x")
        or v.varName.startswith("y")
        or v.varName.startswith("z")
        or v.varName.startswith("o")
    ):
        if v.x != 0:
            print("%s: %g" % (v.varName, v.x))
    else:
        # print retailer decision variables (binary)
        # print('%s: %g' % (v.varName, v.x))
        continue


total_cost = 0
for v in decision_vars:
    if v["part"] == "x":
        DC_amount[v["start"]] += v["var"].x
    elif v["part"] == "y":
        CD_amount[v["start"]] += v["var"].x
    elif v["part"] == "z":
        SOURCE_amount[v["start"]] += v["var"].x
    # else:
    #     OPTIONALSOURCE_amount[v["start"]] += v["var"].x
    #
    # dist = get_distance(distance_data, v["start"], v["dest"])

print(SOURCE_amount)
print(CD_amount)
print(DC_amount)
print(demands)
#print(OPTIONALSOURCE_amount)
print ("Optional cost: {}".format(optionalCost))