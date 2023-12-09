import pandas as pd
from gurobipy import *
from data.constants import *

opt_mod = Model(name="Task3")



# ------------ Decision Variables -----------------



# --- initialize decision_vars ----------------------

decision_vars_attributes = ["var", "part", "start", "dest", "mode"]
decision_vars = []


#decision_vars: list of dicts, one dict correspond to one decision variable. Each decision variable has a GRB.var, part of supply chain (x,y,z), start node, destination node, transport mode, timeBucketstart, timeBucketEnd.
# start node id and destination node id as index
       


#DC to retailers
#attempt using ID as index
for dc in DC:
    for retailer in RETAILER:
        for k in co2cost.keys():
            varname = "x"+k+str(dc["LocationID"])+"-"+str(retailer["LocationID"])
            a = opt_mod.addVar(name=varname, vtype = INTEGER, lb = 0)
            
            var_entry = {
                "var": a,
                "part" : "x", # x = DC to retailer in supply chain
                "start" : dc["LocationID"],
                "dest" : retailer["LocationID"],
                "mode" : k
            }
            decision_vars.append(var_entry)
                
                


for cd in CD:
    for dc in DC:
        for k in co2cost.keys():
            varname = "y"+k+str(cd["LocationID"])+"-"+str(dc["LocationID"])
            a = opt_mod.addVar(name=varname, vtype = INTEGER, lb = 0)
            
            var_entry = {
                "var": a,
                "part" : "y", # y = CD to DC in supply chain
                "start" : cd["LocationID"],
                "dest" : dc["LocationID"],
                "mode" : k
            }
            decision_vars.append(var_entry)




for source in SOURCE:
    for cd in CD:
        for k in co2cost.keys():
            if k == "road":
                continue
            varname = "z"+k+str(source["LocationID"])+"-"+str(cd["LocationID"])
            a = opt_mod.addVar(name=varname, vtype = INTEGER, lb = 0)
            
            var_entry = {
                "var": a,
                "part" : "z", # z = source to CD in supply chain
                "start" : source["LocationID"],
                "dest" : cd["LocationID"],
                "mode" : k
            }
            decision_vars.append(var_entry)
                
 
# ------ Optional Sources -----------

big_M = 1000000

for optionalSource in OPTIONALSOURCE:
    for dc in DC:
        for k in co2cost.keys():
            
            varname = "o" + k + str(optionalSource["LocationID"]) + "-" + str(dc["LocationID"])
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
                "mode": k,
                "build": build
            }
            decision_vars.append(var_entry)


         
# ------ Objective Function --------------------


# objective function: minimize sum of co2 emission to send from DC to Retailer with cost (distance*co2cost) per unit
func1 = (CO2PRICE * sum(list(j["var"]*distance_entry["distance"]*co2cost[j["mode"]] for j in decision_vars for distance_entry in distance_data if distance_entry["start"] == j["start"] and distance_entry["end"] == j["dest"])) / GRAMM_TO_TONNE) 

func2 = sum( list(v["var"] * (slowcost[v["mode"]] + transportcost[v["mode"]]) * get_distance(distance_data, v["start"], v["dest"]) for v in decision_vars))

# pay handling cost in second part of supply chain, i.e. from CD to DC
func3 = sum( list(v["var"] * handlingcost[v["start"]] for v in decision_vars if v["part"] == 'y' or v["part"] == 'x'))

func4 = sum(list(j["var"] * sourcingcost[j["start"]] for j in decision_vars if j["part"] == 'z' for distance_entry in distance_data if distance_entry["start"] == j["start"] and distance_entry["end"] == j["dest"]))

func5 = sum(OPENINGCOST * var_entry["build"] + var_entry["var"] * variablecost[var_entry["start"]] for var_entry in decision_vars if var_entry["part"] == "o")



obj_func = func1 + func2 + func3 + func4 + func5


""" obj_func = sum([item["var"] * co2cost[mode] for item in decision_vars["x"][mode] for mode in co2cost.keys()]) + sum([item["var"] * co2cost[mode] for item in decision_vars["y"][mode] for mode in co2cost.keys()]) + sum([item["var"] * co2cost[mode] for item in decision_vars["z"][mode] for mode in co2cost.keys()]) """

opt_mod.setObjective(obj_func, GRB.MINIMIZE)

# -------------- /set objective function ---------------------



# --- add constraints -------

  
    
for j in decision_vars:
    opt_mod.addConstr(j["var"] >= 0)
    
    
# add constraint for each retailer: sum of amount sent to one retailer = demand of that retailer    
for retailer in demands:
    opt_mod.addConstr(sum(list(j["var"] for j in decision_vars if j["part"] == 'x' and j["dest"] == retailer)) == demands[retailer])
    

# add constraints for each DC: No DC sends out more than its capacity

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
    #amount to send out from this cd
    amount_cd = sum(list(j["var"] for j in decision_vars if j["part"] == 'y' and j["start"] == cd["LocationID"])) 
    opt_mod.addConstr(sum(list(j["var"] for j in decision_vars if j["part"] == 'z' and j["dest"] == cd["LocationID"])) == amount_cd)


# Contraints in Optional Sources are added in the decision variable definition code section


# ----- constraints --------------------------------

opt_mod.optimize()


print("Objective Function Value: %f" % opt_mod.objVal)
current_optimum = opt_mod.objVal


for v in opt_mod.getVars():

    if (v.varName.startswith("x") or v.varName.startswith("y") or v.varName.startswith("z") or v.varName.startswith("o")):
        if v.x != 0:
            print('%s: %g' % (v.varName, v.x))
    else:
        # print retailer decision variables (binary)
        # print('%s: %g' % (v.varName, v.x))
        continue


# --- print costs ---------------------
CO2_emission_cost = 0
transport_cost = 0
slowness_cost = 0
handling_cost_final = 0
variable_cost_final = 0
total_opening_cost = 0
sourcing_cost_final = 0

DC_amount = {key["LocationID"]: 0 for key in DC}
CD_amount = {key["LocationID"]: 0 for key in CD}
SOURCE_amount = {key["LocationID"]: 0 for key in SOURCE}
OPTIONALSOURCE_amount = {key["LocationID"]: 0 for key in OPTIONALSOURCE}



for v in decision_vars:
    
    CO2_emission_cost += v["var"].x * get_distance(distance_data, v["start"], v["dest"]) * co2cost[v["mode"]]*CO2PRICE / GRAMM_TO_TONNE
    transport_cost += v["var"].x * get_distance(distance_data, v["start"], v["dest"]) * transportcost[v["mode"]]
    slowness_cost += v["var"].x * get_distance(distance_data, v["start"], v["dest"]) * slowcost[v["mode"]]
    
    
    if v["part"] == "x":
        DC_amount[v["start"]] += v["var"].x
        handling_cost_final += v["var"].x * handlingcost[v["start"]]
    elif v["part"] == "y":
        CD_amount[v["start"]] += v["var"].x
        handling_cost_final += v["var"].x * handlingcost[v["start"]]
    elif v["part"] == "z":
        SOURCE_amount[v["start"]] += v["var"].x
        sourcing_cost_final += v["var"].x * sourcingcost[v["start"]]
    else:
        OPTIONALSOURCE_amount[v["start"]] += v["var"].x
        variable_cost_final += v["var"].x * variablecost[v["start"]]
        total_opening_cost += v["build"].x * (OPENINGCOST)

print()
print("------- Costs ----------------")
print()
print(f"The minimal total cost in transport and CO2 with optional sources: {current_optimum}$")        
print(f"Cost to compensate CO2 emission: {CO2_emission_cost} $")
print(f"CO2 emission in tonnes: {CO2_emission_cost/CO2PRICE} t")
print(f"Cost to transport the products: {transport_cost + slowness_cost + handling_cost_final}$")
print(f"Transport cost: {transport_cost}$")
print(f"Slowness cost: {slowness_cost}$")
print(f"Sourcing cost: {sourcing_cost_final}")
print(f"Handling cost: {handling_cost_final}$")
print(f"Variable cost: {variable_cost_final}$")
print(f"Opening and operational costs: {total_opening_cost}$")
print(f"Added up: {transport_cost + slowness_cost + sourcing_cost_final + handling_cost_final + variable_cost_final + total_opening_cost + CO2_emission_cost}")
print()


print("------- Amounts --------------")
print(SOURCE_amount)
print(CD_amount)
print(DC_amount)
print(demands)
print(OPTIONALSOURCE_amount)


# ----- print costs ------------------


productionsum = [0,0,0]
for key in DC_amount: #key is locationID
    print("Amount at DC {}: {}; max: {}".format(key, DC_amount[key], DC_constraints[key]))
    #total_cost += DC_amount[key] * handlingcost[key]
    productionsum[0] += DC_amount[key]
    
for key in CD_amount: #key is locationID
    print("Amount at CD {}: {}".format(key, CD_amount[key]))
    #total_cost += CD_amount[key] * handlingcost[key]
    productionsum[1] += CD_amount[key]
    
for key in SOURCE_amount: #key is locationID
    print("Amount at source {}: {}".format(key, SOURCE_amount[key]))
    productionsum[2] += SOURCE_amount[key]
    
print("Assuming that sources and cross-docks have unlimited capacity")
print("Final production sum: ", productionsum)
# ----- calculate monetary cost ---------------------






# ----- Sensitivity Report -------------------------
""" print('Sensitivity Analysis (SA)\nObjVal =', opt_mod.ObjVal)
opt_mod.printAttr(['X', 'Obj', 'SAObjLow', 'SAObjUp'])
opt_mod.printAttr(['X', 'RC', 'LB', 'SALBLow', 'SALBUp', 'UB', 'SAUBLow', 'SAUBUp'])
opt_mod.printAttr(['Sense', 'Slack', 'Pi', 'RHS', 'SARHSLow', 'SARHSUp']) """ # Pi = shadow price = dual variable value
# NOTE: printAttr prints only rows with at least one NON-ZERO value, e.g. model.printAttr('X') prints only non-zero variable values














