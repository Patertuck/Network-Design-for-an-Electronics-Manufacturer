from data.constants import *
from gurobipy import *


class ElectronicManufacturerModel:
    def __init__(self, name):
        self.opt_mod = Model(name=f"{name}")
        self.decision_vars = []
        self.initializeBaseModel()
        self.DC_amount = {key["LocationID"]: 0 for key in DC}
        self.CD_amount = {key["LocationID"]: 0 for key in CD}
        self.SOURCE_amount = {key["LocationID"]: 0 for key in SOURCE}
        self.OPTIONALSOURCE_amount = {key["LocationID"]: 0 for key in OPTIONALSOURCE}

    def initializeBaseModel(self):
        self.addDesicionVariablesZ()
        self.addDesicionVariablesY()
        self.addDesicionVariablesX()
        self.addDesicionVariableO()
        self.addConstraintsNonNegative()
        self.addConstraintRetailers()
        self.addConstraintDc()
        self.addConstraintCd()

    def addDesicionVariablesX(self):
        for dc in DC:
            for retailer in RETAILER:
                for k in co2cost.keys():
                    varname = (
                        "x"
                        + k
                        + str(dc["LocationID"])
                        + "-"
                        + str(retailer["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    var_entry = {
                        "var": a,
                        "part": "x",  # x = DC to retailer in supply chain
                        "start": dc["LocationID"],
                        "dest": retailer["LocationID"],
                        "mode": k,
                    }
                    self.decision_vars.append(var_entry)

    def addDesicionVariablesY(self):
        for cd in CD:
            for dc in DC:
                for k in transportTypes:
                    varname = (
                        "y" + k + str(cd["LocationID"]) + "-" + str(dc["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    var_entry = {
                        "var": a,
                        "part": "y",  # y = CD to DC in supply chain
                        "start": cd["LocationID"],
                        "dest": dc["LocationID"],
                        "mode": k,
                    }
                    self.decision_vars.append(var_entry)

    def addDesicionVariablesZ(self):
        for source in SOURCE:
            for cd in CD:
                for k in transportTypes:
                    if k == "road":
                        continue
                    varname = (
                        "z"
                        + k
                        + str(source["LocationID"])
                        + "-"
                        + str(cd["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)

                    var_entry = {
                        "var": a,
                        "part": "z",  # z = source to CD in supply chain
                        "start": source["LocationID"],
                        "dest": cd["LocationID"],
                        "mode": k,
                    }
                    self.decision_vars.append(var_entry)

    def addDesicionVariableO(self):
        big_M = 10000000000
        for optionalSource in OPTIONALSOURCE:
            for dc in DC:
                for k in transportTypes:
                    varname = (
                        "o"
                        + str(optionalSource["LocationID"])
                        + "-"
                        + str(dc["LocationID"])
                    )
                    a = self.opt_mod.addVar(name=varname, vtype=INTEGER, lb=0)
                    varname_build = varname + "_build"
                    build = self.opt_mod.addVar(name=varname_build, vtype=BINARY)

                    self.opt_mod.addConstr(a >= 0)

                    self.opt_mod.addConstr(a <= big_M * build)

                    var_entry = {
                        "var": a,
                        "part": "o",
                        "start": optionalSource["LocationID"],
                        "dest": dc["LocationID"],
                        "mode": k,
                        "build": build,
                    }
                    self.decision_vars.append(var_entry)

    def addConstraintsNonNegative(self):
        for j in self.decision_vars:
            self.opt_mod.addConstr(j["var"] >= 0)

    def addConstraintRetailers(self):
        for retailer in demands:
            self.opt_mod.addConstr(
                sum(
                    list(
                        j["var"]
                        for j in self.decision_vars
                        if j["part"] == "x" and j["dest"] == retailer
                    )
                )
                == demands[retailer]
            )

    def addConstraintCd(self):
        for cd in CD:
            amount_cd = sum(
                list(
                    j["var"]
                    for j in self.decision_vars
                    if j["part"] == "y" and j["start"] == cd["LocationID"]
                )
            )
            self.opt_mod.addConstr(
                sum(
                    list(
                        j["var"]
                        for j in self.decision_vars
                        if j["part"] == "z" and j["dest"] == cd["LocationID"]
                    )
                )
                == amount_cd
            )

    def addConstraintDc(self):
        for dc in DC:
            amount_dc = sum(
                list(
                    j["var"]
                    for j in self.decision_vars
                    if j["part"] == "x" and j["start"] == dc["LocationID"]
                )
            )
            self.opt_mod.addConstr(amount_dc <= DC_constraints[dc["LocationID"]])
            self.opt_mod.addConstr(
                sum(
                    list(
                        j["var"]
                        for j in self.decision_vars
                        if j["part"] == "y"
                        and j["dest"] == dc["LocationID"]
                        or j["part"] == "o"
                        and j["dest"] == dc["LocationID"]
                    )
                )
                == amount_dc
            )

    def addCo2Const(self, opt_mod, decision_vars, upperBoundCo2):
        self.opt_mod.addConstr(
            sum(
                v["var"] * co2cost[v["mode"]] * distancesMap[v["start"]][v["dest"]]
                for v in decision_vars
            )
            / GRAMM_TO_TONNE
            <= upperBoundCo2
        )

    def getOptimalvalue(self):
        return self.opt_mod.ObjVal

    def getCo2EmissionsInT(self):
        totalEmission = (
            sum(
                v["var"].x * co2cost[v["mode"]] * distancesMap[v["start"]][v["dest"]]
                for v in self.decision_vars
            )
            / GRAMM_TO_TONNE
        )
        return totalEmission

    def getCo2EmissionZ(self):
        emissions = sum(
            (v["var"].x if v["part"] == "z" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getCo2EmissionY(self):
        emissions = sum(
            (v["var"].x if v["part"] == "y" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getCo2EmissionO(self):
        emissions = sum(
            (v["var"].x if v["part"] == "o" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getCo2EmissionX(self):
        emissions = sum(
            (v["var"].x if v["part"] == "x" else 0)
            * distancesMap[v["start"]][v["dest"]]
            * co2cost[v["mode"]]
            for v in self.decision_vars
        )
        return emissions / GRAMM_TO_TONNE

    def getTotalCost(self):
        totalCost = sum(
            j["var"].x
            * (
                distancesMap[j["start"]][j["dest"]]
                * (transportcost[j["mode"]] + slowcost[j["mode"]])
                + locationCosts[j["part"]][j["start"]]
            )
            for j in self.decision_vars
        )
        return totalCost

    def getTransportCost(self):
        transportC = sum(
            v["var"].x * distancesMap[v["start"]][v["dest"]] * transportcost[v["mode"]]
            for v in self.decision_vars
        )
        return transportC

    def getSlownesCost(self):
        slownessCost = sum(
            v["var"].x * distancesMap[v["start"]][v["dest"]] * slowcost[v["mode"]]
            for v in self.decision_vars
        )
        return slownessCost

    def getSourcingCost(self):
        print(sourcingcost)
        sourcingCosts = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "z"
            else 0
            for v in self.decision_vars
        )
        return sourcingCosts

    def getHandlingCostCd(self):
        handlingCosts = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "y"
            else 0
            for v in self.decision_vars
        )
        return handlingCosts

    def getHandlingCostDc(self):
        handlingCosts = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "x"
            else 0
            for v in self.decision_vars
        )
        return handlingCosts

    def getVariableCost(self):
        variableCost = sum(
            (v["var"].x * locationCosts[v["part"]][v["start"]])
            if v["part"] == "o"
            else 0
            for v in self.decision_vars
        )
        return variableCost

    def getOpeningCosts(self):
        openingCosts = 0
        for v in self.decision_vars:
            if v["part"] == "o":
                openingCosts += v["build"].x * (OPENINGCOST)
        return openingcost

    def getLocationAmounts(self):
        for v in self.decision_vars:
            if v["part"] == "x":
                self.DC_amount[v["start"]] += v["var"].x
            elif v["part"] == "y":
                self.CD_amount[v["start"]] += v["var"].x
            elif v["part"] == "z":
                self.SOURCE_amount[v["start"]] += v["var"].x
            else:
                self.OPTIONALSOURCE_amount[v["start"]] += v["var"].x

    def report(self):
        print()
        print("----------- start report ----------")
        print()
        print(f"Objective Function Value: {self.getOptimalvalue()}")
        print()
        print("------- Nodes --------")
        print()
        for v in self.opt_mod.getVars():
            if (
                v.varName.startswith("x")
                or v.varName.startswith("y")
                or v.varName.startswith("z")
                or v.varName.startswith("o")
            ):
                if v.x != 0:
                    print("%s: %g" % (v.varName, v.x))
        print()
        print("------- Costs --------")
        print()
        print(f"Total cost: {self.getTotalCost()} Euro")
        print(f"Slowness cost: {self.getSlownesCost()} Euro")
        print(f"Transportation cost: {self.getTransportCost()} Euro")
        print(f"Sourcing costs: {self.getSourcingCost()} Euro")
        print(f"Handling costs at cross docs: {self.getHandlingCostCd()} Euro")
        print(
            f"Handling costs at distribution centers: {self.getHandlingCostDc()} Euro"
        )
        print(f"Variable costs at optional source: {self.getVariableCost()} Euro")
        print(f"Opening costs at optional source: {self.getOpeningCosts()} Euro")
        print()
        print("------- Emissions -------")
        print()
        print(f"Total Co2 emissions: {self.getCo2EmissionsInT()}t")
        print(f"Cost for compensation: {self.getCo2EmissionsInT() * CO2PRICE} Euro")
        print(f"Emissions between retailer and cross doc: {self.getCo2EmissionZ()} t")
        print(
            f"Emissions between cross doc and dsitribution center: {self.getCo2EmissionY()} t"
        )
        print(
            f"Emissions between optional source and distribution center: {self.getCo2EmissionO()} t"
        )
        print(
            f"Emissions between distribution center and retailer: {self.getCo2EmissionX()} t"
        )
        print()
        print(("--------- Amouts --------"))
        print()
        print(f"Sources: {SOURCE_amount}")
        print(f"Cross Docs: {CD_amount}")
        print(f"Distribution centers: {DC_amount}")
        print(f"Demands ad retailers: {demands}")
        print(f"Optional sources: {OPTIONALSOURCE_amount}")
        print()
        print("--------- end report ------------")
        print()

    def minCostsOnlyAir(self):
        minCosts = sum(
            j["var"]
            * (
                get_distance(distance_data, j["start"], j["dest"])
                * (transportcost["air"])
                + locationCosts[j["part"]][j["start"]]
            )
            for j in self.decision_vars
        )
        return minCosts

    def minCostsAlltransport(self):
        minCosts = sum(
            j["var"]
            * (
                distancesMap[j["start"]][j["dest"]]
                * (transportcost[j["mode"]] + slowcost[j["mode"]])
                + locationCosts[j["part"]][j["start"]]
            )
            for j in self.decision_vars
        )
        return minCosts

    def minCo2OptionalSources(self):
        func1 = (
            CO2PRICE
            * sum(
                list(
                    j["var"] * distance_entry["distance"] * co2cost[j["mode"]]
                    for j in self.decision_vars
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
                for v in self.decision_vars
            )
        )

        func3 = sum(
            list(
                v["var"] * handlingcost[v["start"]]
                for v in self.decision_vars
                if v["part"] == "y" or v["part"] == "x"
            )
        )

        func4 = sum(
            list(
                j["var"] * sourcingcost[j["start"]]
                for j in self.decision_vars
                if j["part"] == "z"
                for distance_entry in distance_data
                if distance_entry["start"] == j["start"]
                and distance_entry["end"] == j["dest"]
            )
        )

        func5 = sum(
            OPENINGCOST * var_entry["build"]
            + var_entry["var"] * variablecost[var_entry["start"]]
            for var_entry in self.decision_vars
            if var_entry["part"] == "o"
        )

        return func1 + func2 + func3 + func4 + func5

    def minCostsWithO(self):
        obj_func = (
            sum(
                j["var"] * distance_entry["distance"] * transportcost["air"]
                for j in minCostsWithO.decision_vars
                for distance_entry in distance_data
                if distance_entry["start"] == j["start"]
                and distance_entry["end"] == j["dest"]
            )
            + sum(
                l["var"] * variablecost[l["start"]]
                for l in minCostsWithO.decision_vars
                if l["part"] == "o"
            )
            + sum(
                1250000 * var_entry["build"]
                for var_entry in minCostsWithO.decision_vars
                if var_entry["part"] == "o"
            )
            + sum(
                j["var"] * sourcingcost[j["start"]]
                for j in minCostsWithO.decision_vars
                if j["part"] == "z"
            )
            + sum(
                j["var"] * handlingcost[j["start"]]
                for j in minCostsWithO.decision_vars
                if j["part"] == "y" or j["part"] == "x"
            )
        )
        return obj_func


# add or choose opjective function
minCostsWithO = ElectronicManufacturerModel("Os")
obj_func = minCostsWithO.minCostsWithO()
minCostsWithO.opt_mod.setObjective(obj_func, GRB.MINIMIZE)
minCostsWithO.opt_mod.optimize()
minCostsWithO.report()
