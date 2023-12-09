import pandas as pd
from gurobipy import *
from data.constants import *

opt_mod = Model(name="Task3")
GRAMM_TO_TONNE = 1000000


# ------------ Decision Variables -----------------

# --- initialize decision_vars ----------------------


# For each retailer, create binary decision variable for whether or not we should ship to them
# linear cost if dec_var == 1, 50000 if dec_var == 0

retailer_decision_vars = []
# retailer_decision_vars is a list of dicts: {var: GRB.var, LocationID, Position, Role, NodeID}

for i in RETAILER:
    # i = 1 means sending to retailer
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
            a = opt_mod.addVar(name=varname, vtype=CONT, lb=0)

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
            a = opt_mod.addVar(name=varname, vtype=CONT, lb=0)

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
            a = opt_mod.addVar(name=varname, vtype=CONT, lb=0)

            var_entry = {
                "var": a,
                "part": "z",  # z = source to CD in supply chain
                "start": source["LocationID"],
                "dest": cd["LocationID"],
                "mode": k,
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


# objective function: minimize sum of co2 emission to send from DC to Retailer with cost (distance*co2cost) per unit
func1 = (
    CO2PRICE
    * sum(
        list(
            j["var"] * distance_entry["distance"] * co2cost[j["mode"]]
            for j in decision_vars
            for distance_entry in distance_data
            if distance_entry["start"] == j["start"]
            and distance_entry["end"] == j["dest"]
        )
    )
    / GRAMM_TO_TONNE
)

func2 = sum(
    list(
        v["var"]
        * (slowcost[v["mode"]] + transportcost[v["mode"]])
        * get_distance(distance_data, v["start"], v["dest"])
        for v in decision_vars
    )
)

# pay handling cost in second part of supply chain, i.e. from CD to DC
func3 = sum(
    list(
        v["var"] * handlingcost[v["start"]]
        for v in decision_vars
        if v["part"] == "y" or v["part"] == "x"
    )
)

func4 = sum(
    list(
        j["var"] * sourcingcost[j["start"]]
        for j in decision_vars
        if j["part"] == "z"
        for distance_entry in distance_data
        if distance_entry["start"] == j["start"] and distance_entry["end"] == j["dest"]
    )
)


obj_func = func1 + func2 + func3 + func4


""" obj_func = sum([item["var"] * co2cost[mode] for item in decision_vars["x"][mode] for mode in co2cost.keys()]) + sum([item["var"] * co2cost[mode] for item in decision_vars["y"][mode] for mode in co2cost.keys()]) + sum([item["var"] * co2cost[mode] for item in decision_vars["z"][mode] for mode in co2cost.keys()]) """

opt_mod.setObjective(obj_func, GRB.MINIMIZE)

# --- set objective function


# --- add constraints -------


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


# ----- constraints --------------------------------

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
        # print retailer decision variables (binary)
        # print('%s: %g' % (v.varName, v.x))
        continue


# --- print costs ---------------------
CO2_emission_cost = 0
transport_cost = 0
slowness_cost = 0
handling_cost = 0
sourcing_cost = 0


for v in decision_vars:
    CO2_emission_cost += (
        v["var"].x
        * get_distance(distance_data, v["start"], v["dest"])
        * co2cost[v["mode"]]
        * CO2PRICE
        / GRAMM_TO_TONNE
    )
    transport_cost += (
        v["var"].x
        * get_distance(distance_data, v["start"], v["dest"])
        * transportcost[v["mode"]]
    )
    slowness_cost += (
        v["var"].x
        * get_distance(distance_data, v["start"], v["dest"])
        * slowcost[v["mode"]]
    )

    if v["part"] == "x":
        DC_amount[v["start"]] += v["var"].x
        handling_cost += v["var"].x * (handlingcost[v["start"]])

    elif v["part"] == "y":
        CD_amount[v["start"]] += v["var"].x
        # add handling cost if the decision variable goes from CD to DC
        handling_cost += v["var"].x * (handlingcost[v["start"]])

    else:
        SOURCE_amount[v["start"]] += v["var"].x
        sourcing_cost += v["var"].x * sourcingcost[v["start"]]

print()
print(
    f"Given the CO2 price of {CO2PRICE}$ per tonne, the minimal total cost: {current_optimum}$"
)
print(
    f"Added up: {transport_cost + slowness_cost + handling_cost + sourcing_cost + CO2_emission_cost}"
)
print(f"Cost to compensate CO2 emission: {CO2_emission_cost}$")
print(f"CO2 emission in tonnes: {CO2_emission_cost/CO2PRICE}t")
print(
    f"Cost to transport the products (sourcing cost): {transport_cost + slowness_cost + handling_cost}$"
)
print(f"Transport cost: {transport_cost}$")
print(f"Slowness cost: {slowness_cost} $")
print(f"Sourcing cost: {sourcing_cost}$")
print(f"Handling cost: {handling_cost}$")
print()

# ----- print costs ------------------


productionsum = [0, 0, 0]
for key in DC_amount:  # key is locationID
    print(
        "Amount at DC {}: {}; max: {}".format(key, DC_amount[key], DC_constraints[key])
    )
    # total_cost += DC_amount[key] * handlingcost[key]
    productionsum[0] += DC_amount[key]

for key in CD_amount:  # key is locationID
    print("Amount at CD {}: {}".format(key, CD_amount[key]))
    # total_cost += CD_amount[key] * handlingcost[key]
    productionsum[1] += CD_amount[key]

for key in SOURCE_amount:  # key is locationID
    print("Amount at source {}: {}".format(key, SOURCE_amount[key]))
    productionsum[2] += SOURCE_amount[key]

print("Assuming that sources and cross-docks have unlimited capacity")
print("Final production sum: ", productionsum)
# ----- calculate monetary cost ---------------------


# ----- Sensitivity Report -------------------------
""" print('Sensitivity Analysis (SA)\nObjVal =', opt_mod.ObjVal)
opt_mod.printAttr(['X', 'Obj', 'SAObjLow', 'SAObjUp'])
opt_mod.printAttr(['X', 'RC', 'LB', 'SALBLow', 'SALBUp', 'UB', 'SAUBLow', 'SAUBUp'])
opt_mod.printAttr(['Sense', 'Slack', 'Pi', 'RHS', 'SARHSLow', 'SARHSUp']) """  # Pi = shadow price = dual variable value
# NOTE: printAttr prints only rows with at least one NON-ZERO value, e.g. model.printAttr('X') prints only non-zero variable values
