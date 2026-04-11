import flash.external.ExternalInterface;
import UI.UIOrder;
import UI.pet.PetUI;
import com.adobe.crypto.MD5;
import com.common.text.TextWay;
import com.sounto.cf.ObjectToXml;
import com.adobe.serialization.json.JSON2;
import dataAll.equip.define.EquipType;
import dataAll._player.base.PlayerBaseData;
import dataAll._player.more.MorePlayerData;
import gameAll.body.IO_NormalBody;
import dataAll._app.edit.card.BossCardCreator;
import dataAll._app.goods.define.PriceType;
import dataAll._app.task.define.TaskType;
import dataAll._app.task.TaskData;
import dataAll.gift.GiftAddit;
import dataAll.body.attack.ElementHurt;
import dataAll.arms.creator.ArmsEvoCtrl;
import dataAll.arms.creator.ArmsStrengthenCtrl;
import dataAll.equip.EquipPropertyData;
import dataAll.equip.creator.EquipEvoCtrl;
import dataAll.equip.creator.EquipStrengthenCtrl;
import dataAll.equip.vehicle.VehicleDataCreator;
import dataAll.equip.jewelry.JewelryDataCreator;
import dataAll.equip.shield.ShieldDataCreator;
import dataAll.equip.weapon.WeaponDataCreator;
import dataAll.equip.device.DeviceDataCreator;
import dataAll._app.union.info.MemberListInfo;

ExternalInterface.addCallback("change", change);

public function toColor(cnName:String):String {
    var DICT_COLOR:Object = {"白": "white",
            "绿": "green",
            "蓝": "blue",
            "紫": "purple",
            "橙": "orange",
            "红": "red",
            "黑": "black",
            "暗金": "darkgold",
            "紫金": "purgold",
            "氩星": "yagold"};
    return DICT_COLOR.hasOwnProperty(cnName) ? DICT_COLOR[cnName] : "red";
}

public function fleshUIBox(box:String, label:String):void {
    var UI:* = Gaming.uiGroup[box];
    if (!UI.visible) {
        UIShow.hideNowApp();
        UI.show();
    }
    UI.showBox(label);
}

public function getUnionMemberInfoToText(unionMemberInfoArr:*):String {
    var infoArr:Array = ["rank", "getNickName", "getRoleCnNameInList", "getMilitaryCnName", "extraObj.vip", "getDpsStringNoColor", "getLifeStringNoColor", "getBattleString", "getBattleMapCn", "getLoginTime", "getWeekContribution", "getWeekContribution_1", "getWeekContribution_2", "contribution", "uId", "index"];
    var infoCnArr:Array = ["排名", "昵称", "职位", "军衔", "VIP", "战斗力", "生命值", "周争霸分数", "周争霸地图", "最近登录日期", "周贡献", "上周贡献", "上上周贡献", "总贡献", "UID", "索引"];
    var infoData:String = infoCnArr + "";
    var unionMemberInfo:* = null;
    for each (unionMemberInfo in unionMemberInfoArr) {
        infoData += "\n" + unionMemberInfo.getStringArrBy(infoArr);
    }
    return infoData;
}

public function getSkillByCn(cnName:String):String {
    var skillDefObj:Object = Gaming.defineGroup.skill.obj;
    if (skillDefObj.hasOwnProperty(cnName)) {
        return cnName;
    }
    var skillDef:* = null;
    for each (skillDef in skillDefObj) {
        if (skillDef.cnName == cnName) {
            return skillDef.name;
        }
    }
    return "";
}

public function getSkillArrByCnArr(cnNameArr:Array):Array {
    var cnName:String = "";
    var nameArr:Array = [];
    var skillDef:* = null;
    var skillDefObj:Object = Gaming.defineGroup.skill.obj;
    for each (cnName in cnNameArr) {
        if (skillDefObj.hasOwnProperty(cnName)) {
            nameArr.push(cnName);
        }
        for each (skillDef in skillDefObj) {
            if (skillDef.cnName == cnName) {
                nameArr.push(skillDef.name);
                break;
            }
        }
    }
    return nameArr;
}

public function getOneTypeSkillArrByCnArr(cnNameArr:Array, father:String):Array {
    var cnName:String = "";
    var nameArr:Array = [];
    var skillDef:* = null;
    var skillDefArr:Array = Gaming.defineGroup.skill.getArrByFather(father);
    for each (cnName in cnNameArr) {
        for each (skillDef in skillDefArr) {
            if (skillDef.cnName == cnName) {
                nameArr.push(skillDef.name);
                break;
            }
        }
    }
    return nameArr;
}

public function getPetStudySkillDefByCn(petData:*, cnName:String):* {
    var petSkillDef:* = null;
    var petSkill:String = "";
    var petSkillArr:Array = petData.gene.save.getAllSkillArr();
    for each (petSkill in petSkillArr) {
        petSkillDef = Gaming.defineGroup.skill.getDefine(petSkill);
        if (petSkillDef && petSkillDef.cnName == cnName) {
            return petSkillDef;
        }
    }
    return null;
}

public function getVehicleStudySkillDefByCn(vehicleData:*, cnName:String):* {
    var vehicleSkillDef:* = null;
    var vehicleSkill:String = "";
    var vehicleSkillArr:Array = vehicleData.vehicleDefine.skillArr;
    for each (vehicleSkill in vehicleSkillArr) {
        vehicleSkillDef = Gaming.defineGroup.skill.getDefine(vehicleSkill);
        if (vehicleSkillDef && vehicleSkillDef.cnName == cnName) {
            return vehicleSkillDef;
        }
    }
    return null;
}

public function getAllPartsDefArr():Array {
    var thingsDef:* = null;
    var thingsDefObj:Object = Gaming.defineGroup.things.obj;
    var partsDefArr:Array = [];
    for each (thingsDef in thingsDefObj) {
        if ((thingsDef.isPartsB() || thingsDef.isElePartsB() || thingsDef.isPartsSpecialB() || thingsDef.isPartsRareB() || thingsDef.isPartsNormalB()) && (thingsDef.name.indexOf("_") != -1)) {
            partsDefArr.push(thingsDef);
        }
    }
    return partsDefArr;
}

public function getAllProDefArr():Array {
    var proDef:* = null;
    var equipPro:String = "";
    var equipProArr:Array = EquipPropertyData.pro_arr;
    var suitProArr:Array = Gaming.defineGroup.suitProperty.propertyArr;
    for each (equipPro in equipProArr) {
        proDef = Gaming.defineGroup.getPropertyArrayDefine(equipPro);
        if (Boolean(proDef)) {
            suitProArr.push(proDef);
        }
    }
    return suitProArr;
}

public function getProByCn(cnName:String):String {
    var proDef:* = null;
    var proDefArr:Array = getAllProDefArr();
    for each (proDef in proDefArr) {
        if (proDef.cnName == cnName) {
            return proDef.name;
        }
    }
    return "";
}

public function getPetProByCn(cnName:String):String {
    var proDef:* = null;
    var proDefArr:Array = Gaming.defineGroup.gene.pro.propertyArr;
    for each (proDef in proDefArr) {
        if (proDef.cnName == cnName) {
            return proDef.name;
        }
    }
    return "";
}

public function getPeakProByCn(cnName:String):String {
    var proDef:* = null;
    var proDefArr:Array = Gaming.defineGroup.peakPro.arr;
    for each (proDef in proDefArr) {
        if (proDef.cnName == cnName) {
            return proDef.name;
        }
    }
    return "";
}

public function getUnendProByCn(cnName:String):String {
    var proDef:* = null;
    var proDefArr:Array = Gaming.defineGroup.unend.proG.arr;
    for each (proDef in proDefArr) {
        if (proDef.cnName == cnName) {
            return proDef.name;
        }
    }
    return "";
}

public function getArmsRangeDefByCn(cnName:String):* {
    var bulletDef:* = Gaming.defineGroup.bullet;
    var rangeDef:* = null;
    var rangeDefArr:Array = bulletDef.rareArmsRangeArr;
    rangeDefArr = rangeDefArr.concat(bulletDef.blackArmsRangeArr);
    rangeDefArr = rangeDefArr.concat(bulletDef.darkgoldArmsRangeArr);
    rangeDefArr = rangeDefArr.concat(bulletDef.purgoldArmsRangeArr);
    rangeDefArr = rangeDefArr.concat(bulletDef.yagoldArmsRangeArr);
    for each (rangeDef in rangeDefArr) {
        if (rangeDef.def.cnName == cnName) {
            return rangeDef;
        }
    }
    return null;
}

public function getArmsElementHurtByCn(cnName:String):String {
    var eleHurt:String = "";
    var eleHurtAttr:String = "";
    var eleHurtArr:Array = ElementHurt.arr;
    for each (eleHurtAttr in eleHurtArr) {
        eleHurt = ElementHurt[eleHurtAttr];
        if (ElementHurt.getCn(eleHurt) == cnName) {
            return eleHurt;
        }
    }
    return "";
}

public function getEquipDefByCn(cnName:String):* {
    var equipDef:* = null;
    var equipDefObj:Object = Gaming.defineGroup.equip.obj;
    for each (equipDef in equipDefObj) {
        if (equipDef.cnName == cnName) {
            return equipDef;
        }
    }
    return null;
}

public function getEquipPartTypeByCn(cnName:String):String {
    var n:Number = 0;
    var equipTypeArr:Array = EquipType.TYPE_ARR;
    var equipTypeCnArr:Array = EquipType.TYPE_CN_ARR;
    for (n in equipTypeCnArr) {
        if (equipTypeCnArr[n] == cnName) {
            return equipTypeArr[n];
        }
    }
    return "";
}

public function isMaxStrengthenLv(itemSave:*, strengthenCtrl:*):Boolean {
    return itemSave.strengthenLv >= strengthenCtrl.maxAddLevel;
}

public function clamp(value:*, min:int, max:int):int {
    if (min > max) {
        return 0;
    }
    var val:Number = Number(value);
    return int(val < min ? min : (val > max ? max : val));
}

public function copy(data:String):void {
    ExternalInterface.call("function(data) {const dom = document.createElement('textarea');dom.value = data;document.body.appendChild(dom);dom.select();document.execCommand('copy');document.body.removeChild(dom);}", data);
}

public function change(mode:String, type:String, method:String, string:String, number:Number):void {
    switch (mode) {
        case "normal":
            testCtrl.cheating.doOrder(type, method, string, number);
            break;
        case "extend":
            var extendMethods:Object = {"hero": {
                        "playerName": function(text:String, value:Number):String
                        {
                            return this.changePlayerObj("base", "playerName", text);
                        },
                        "level": function(text:String, value:Number):String
                        {
                            return this.changePlayerObj("base", "level", value);
                        },
                        "exp": function(text:String, value:Number):String
                        {
                            return this.changePlayerObj("base", "exp", value);
                        },
                        "arms": function(text:String, value:Number):String
                        {
                            return this.changePlayerObj("arms", "unlockTo", value, true);
                        },
                        "skill": function(text:String, value:Number):String
                        {
                            return this.changePlayerObj("skill", "unlockTo", value, true);
                        },
                        "changePlayerObj": function(type:String, attr:String, value:*, isMethod:Boolean = false):String
                        {
                            var dataGroup:* = Gaming.PG.DATA[type];
                            if (isMethod) {
                                dataGroup.saveGroup[attr](value);
                            } else {
                                dataGroup.save[attr] = value;
                            }
                            Gaming.uiGroup.moreBox.fleshData();
                            Gaming.uiGroup.wearUI.fleshAllBox();
                            return "设置[" + type + "][" + attr + "]:" + value;
                        }
                    }, "drop": {
                        "deviceNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("deviceNum", value);
                        },
                        "weaponNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("weaponNum", value);
                        },
                        "normalChestNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("normalChestNum", value);
                        },
                        "magicChestNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("magicChestNum", value);
                        },
                        "tigerChest": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("tigerChest", value);
                        },
                        "keyNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("keyNum", value);
                        },
                        "bloodStoneNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("bloodStoneNum", value);
                        },
                        "blackChipNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("blackChipNum", value);
                        },
                        "allBlackChipNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("allBlackChipNum", value);
                        },
                        "armsBlackChipNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("armsBlackChipNum", value);
                        },
                        "allArmsBlackChipNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("allArmsBlackChipNum", value);
                        },
                        "partsNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("partsNum", value);
                        },
                        "equipGem": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("equipGem", value);
                        },
                        "ironChiefBook": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("ironChiefBook", value);
                        },
                        "madheart": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("madheart", value);
                        },
                        "mhA": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("mhA", value);
                        },
                        "nintyEquipBlackNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("nintyEquipBlackNum", value);
                        },
                        "allNintyEquipBlackNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("allNintyEquipBlackNum", value);
                        },
                        "nintyArmsBlackNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("nintyArmsBlackNum", value);
                        },
                        "allNintyArmsBlackNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("allNintyArmsBlackNum", value);
                        },
                        "dragonChestNum": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("dragonChestNum", value);
                        },
                        "timeCMore": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("timeCMore", value);
                        },
                        "arenaStamp": function(text:String, value:Number):String
                        {
                            return this.changeDropObj("arenaStamp", value);
                        },
                        "weekObj": function(text:String, value:Number):String
                        {
                            return this.changeDropRecordObj("weekObj", text, value);
                        },
                        "dayObj": function(text:String, value:Number):String
                        {
                            return this.changeDropRecordObj("dayObj", text, value);
                        },
                        "dayAll": function(text:String, value:Number):String
                        {
                            return this.changeDropRecordObj("dayAll", text, value);
                        },
                        "changeDropObj": function(attr:String, value:Number):String
                        {
                            Gaming.PG.save.drop[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        },
                        "changeDropRecordObj": function(type:String, attr:String, value:Number):String
                        {
                            var thingsDef:* = Gaming.defineGroup.things.getDefineByCnName(attr);
                            if (thingsDef && !thingsDef.isPartsB() && !thingsDef.isShopAutoUseB()) {
                                var thingsName:String = thingsDef.name;
                                Gaming.PG.save.drop[type].setAttribute(thingsName, value);
                                return "设置[" + type + "][" + thingsName + "]:" + value;
                            }
                            return "未找到物品(材料/碎片):" + attr;
                        }
                    }, "more": {
                        "add": function(text:String, value:Number):String
                        {
                            var bodyDef:* = Gaming.defineGroup.body.getCnDefine(text);
                            if (bodyDef) {
                                Gaming.PG.da.moreBag.addByUnitName(bodyDef.name);
                                Gaming.PG.da.more.swapByOther(Gaming.PG.da.moreBag, 1, 0);
                                UIShow.main();
                                return "添加队友:" + text;
                            }
                            return "未找到实体:" + text;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("remove");
                        },
                        "exploit": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("partner", "exploit", value);
                        },
                        "love": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("love", "value", value);
                        },
                        "attack": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("partner", "attack", value, true);
                        },
                        "defence": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("partner", "defence", value, true);
                        },
                        "dieNum": function(text:String, value:Number):String
                        {
                            return this.changeMoreCount("dieNum", value);
                        },
                        "killNum": function(text:String, value:Number):String
                        {
                            return this.changeMoreCount("killNum", value);
                        },
                        "killBossNum": function(text:String, value:Number):String
                        {
                            return this.changeMoreCount("killBossNum", value);
                        },
                        "allGivingNum": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("love", "allGivingNum", value);
                        },
                        "hateGiftNum": function(text:String, value:Number):String
                        {
                            return this.changeMoreObj("love", "hateGiftNum", value);
                        },
                        "lockLen": function(text:String, value:Number):String
                        {
                            Gaming.PG.save.more.lockLen = value;
                            return "设置可上场队友数量:" + value;
                        },
                        "changeMoreObj": function(type:String, attr:String = "", value:* = null, isMethod:Boolean = false):String
                        {
                            var moreData:MorePlayerData = Gaming.PG.DATA as MorePlayerData;
                            if (moreData) {
                                var tipText:String = "";
                                var moreDataSave:* = moreData[type].save;
                                if (type == "remove") {
                                    var heroData:* = moreData.heroData;
                                    if (heroData.isFightB()) {
                                        Gaming.PG.da.more.removeData(heroData);
                                    } else {
                                        Gaming.PG.da.moreBag.removeData(heroData);
                                    }
                                    tipText = "删除:" + heroData.def.cnName;
                                } else {
                                    if (isMethod) {
                                        moreDataSave.setPoint(attr, value);
                                    } else {
                                        moreDataSave[attr] = value;
                                    }
                                    tipText = "设置[" + type + "][" + attr + "]:" + value;
                                }
                                Gaming.uiGroup.moreBox.fleshData();
                                Gaming.uiGroup.moreBox.chooseMainData();
                                Gaming.uiGroup.wearUI.fleshAllBox();
                                return tipText;
                            }
                            return "未找到队友";
                        },
                        "changeMoreCount": function(attr:String, value:Number):String
                        {
                            var moreData:MorePlayerData = Gaming.PG.DATA as MorePlayerData;
                            if (moreData) {
                                moreData.getNormalSave().count[attr] = value;
                                return "设置[" + attr + "]:" + value;
                            }
                            return "未找到队友";
                        }
                    }, "bag": {
                        "armsBag": function(text:String, value:Number):String
                        {
                            return this.unlockBag("armsBag", value);
                        },
                        "equipBag": function(text:String, value:Number):String
                        {
                            return this.unlockBag("equipBag", value);
                        },
                        "thingsBag": function(text:String, value:Number):String
                        {
                            return this.unlockBag("thingsBag", value);
                        },
                        "geneBag": function(text:String, value:Number):String
                        {
                            return this.unlockBag("geneBag", value);
                        },
                        "partsBag": function(text:String, value:Number):String
                        {
                            return this.unlockBag("partsBag", value);
                        },
                        "pet": function(text:String, value:Number):String
                        {
                            return this.unlockBag("pet", value, false);
                        },
                        "bossCard": function(text:String, value:Number):String
                        {
                            Gaming.PG.save.bossCard.bag = Number(value - 100);
                            Gaming.uiGroup.bosseditUI.fleshCardBox();
                            return "解锁[bossCard]:" + value;
                        },
                        "armsHouse": function(text:String, value:Number):String
                        {
                            return this.unlockBag("armsHouse", value);
                        },
                        "equipHouse": function(text:String, value:Number):String
                        {
                            return this.unlockBag("equipHouse", value);
                        },
                        "unlockAll": function(text:String, value:Number):String
                        {
                            this.unlockBag("arms", 0, true, true);
                            this.unlockBag("skill", 0, true, true);
                            this.unlockBag("armsBag", 0, true, true);
                            this.unlockBag("equipBag", 0, true, true);
                            this.unlockBag("thingsBag", 0, true, true);
                            this.unlockBag("geneBag", 0, true, true);
                            this.unlockBag("partsBag", 0, true, true);
                            this.unlockBag("armsHouse", 0, true, true);
                            this.unlockBag("equipHouse", 0, true, true);
                            this.unlockBag("pet", 999, false);
                            return "解锁所有格子";
                        },
                        "unlockBag": function(type:String, value:Number, isMethod:Boolean = true, isUnlockAll:Boolean = false):String
                        {
                            var dataGroup:* = Gaming.PG.da[type];
                            var saveGroup:* = dataGroup.saveGroup;
                            if (isUnlockAll) {
                                value = saveGroup.gripMaxNum;
                            }
                            if (isMethod) {
                                saveGroup.unlockTo(value);
                            } else {
                                saveGroup.lockLen = value;
                            }
                            if (type == "pet") {
                                Gaming.uiGroup.petUI.fleshData();
                            } else if (dataGroup.placeType == "bag") {
                                Gaming.uiGroup.bagUI.fleshAllBox();
                            } else {
                                Gaming.uiGroup.houseUI.fleshData();
                            }
                            return "解锁[" + type + "]:" + value;
                        },
                        "clear_armsBag": function(text:String, value:Number):String
                        {
                            return this.clearBag("armsBag");
                        },
                        "clear_equipBag": function(text:String, value:Number):String
                        {
                            return this.clearBag("equipBag");
                        },
                        "clear_thingsBag": function(text:String, value:Number):String
                        {
                            return this.clearBag("thingsBag");
                        },
                        "clear_geneBag": function(text:String, value:Number):String
                        {
                            return this.clearBag("geneBag");
                        },
                        "clear_partsBag": function(text:String, value:Number):String
                        {
                            return this.clearBag("partsBag");
                        },
                        "clear_pet": function(text:String, value:Number):String
                        {
                            return this.clearBag("pet");
                        },
                        "clear_armsHouse": function(text:String, value:Number):String
                        {
                            return this.clearBag("armsHouse");
                        },
                        "clear_equipHouse": function(text:String, value:Number):String
                        {
                            return this.clearBag("equipHouse");
                        },
                        "clearBag": function(type:String):String
                        {
                            var dataGroup:* = Gaming.PG.da[type];
                            dataGroup.clearData();
                            if (type == "pet") {
                                Gaming.uiGroup.petUI.fleshData();
                            } else if (dataGroup.placeType == "bag") {
                                Gaming.uiGroup.bagUI.fleshAllBox();
                            } else {
                                Gaming.uiGroup.houseUI.fleshData();
                            }
                            return "删除所有:" + type;
                        }
                    }, "map": {
                        "unlockOne": function(text:String, value:Number):String
                        {
                            var worldMapDef:* = Gaming.defineGroup.worldMap.getDefineByCn(text);
                            if (worldMapDef && worldMapDef.father == "infected_area") {
                                Gaming.PG.da.worldMap.saveGroup.unlockOne(worldMapDef.name);
                                Gaming.PG.da.worldMap.saveGroup.winOne(worldMapDef.name, 9);
                                Gaming.uiGroup.mainUI.show();
                                return "解锁地图:" + text;
                            }
                            return "未找到地图:" + text;
                        },
                        "unlockAll": function(text:String, value:Number):String
                        {
                            Gaming.PG.da.worldMap.saveGroup.unlockAll();
                            Gaming.PG.da.worldMap.saveGroup.winAll();
                            Gaming.PG.da.worldMap.saveGroup.unlockAllDiff();
                            Gaming.uiGroup.mainUI.show();
                            return "解锁所有地图";
                        },
                        "winNum": function(text:String, value:Number):String
                        {
                            return this.changeMapCount(text, "winNum", value, true);
                        },
                        "rebirthNum": function(text:String, value:Number):String
                        {
                            return this.changeMapCount(text, "rebirthNum", value);
                        },
                        "bulletNum": function(text:String, value:Number):String
                        {
                            return this.changeMapCount(text, "bulletNum", value);
                        },
                        "time": function(text:String, value:Number):String
                        {
                            return this.changeMapCount(text, "time", value);
                        },
                        "star": function(text:String, value:Number):String
                        {
                            return this.changeMapCount(text, "star", value);
                        },
                        "changeMapCount": function(map:String, attr:String, value:Number, isProp:Boolean = false):String {
                            var worldMapDef:* = Gaming.defineGroup.worldMap.getDefineByCn(map);
                            var worldMapSave:* = null;
                            var worldMapSaveObj:Object = Gaming.PG.da.worldMap.saveGroup.obj;
                            if (worldMapDef && worldMapDef.father == "infected_area") {
                                for each (worldMapSave in worldMapSaveObj) {
                                    if (worldMapSave.name == worldMapDef.name) {
                                        if (isProp) {
                                            worldMapSave[attr] = value;
                                        } else {
                                            worldMapSave.countSave[attr] = value;
                                        }
                                        return "设置[" + attr + "]:" + value;
                                    }
                                }
                                return "未解锁地图:" + map;
                            }
                            return "未找到地图:" + map;
                        }
                    }, "level": {
                        "over": function(text:String, value:Number):String
                        {
                            Gaming.LG.levelWin("r_over");
                            return "通关";
                        },
                        "restart": function(text:String, value:Number):String
                        {
                            Gaming.LG.restartLevel();
                            return "重玩";
                        },
                        "killAllEnemy": function(text:String, value:Number):String
                        {
                            var n:Number = 0;
                            var enemyBody:IO_NormalBody = null;
                            var enemyArr:Array = Gaming.BG.ENEMY_ARR;
                            for each (enemyBody in enemyArr) {
                                Gaming.TG.hurt.toDie(enemyBody);
                                n++;
                            }
                            return "杀死敌方所有实体:" + n + "个";
                        }
                    }, "wilder": {
                        "unlockAllWider": function(text:String, value:Number):String
                        {
                            Gaming.PG.da.wilder.unlockAllWider();
                            return "解锁所有秘境";
                        },
                        "wilderKeyNum": function(text:String, value:Number):String
                        {
                            Gaming.PG.save.wilder.keyNum = value;
                            return "设置秘境钥匙:" + value;
                        }
                    }, "count": {
                        "dieNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("dieNum", value);
                        },
                        "killNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("killNum", value);
                        },
                        "killBossNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("killBossNum", value);
                        },
                        "weaponKillNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("weaponKillNum", value);
                        },
                        "vehicleKillNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("vehicleKillNum", value);
                        },
                        "dropArmsNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("dropArmsNum", value);
                        },
                        "dropEquipNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("dropEquipNum", value);
                        },
                        "bossNoOrangeNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("bossNoOrangeNum", value);
                        },
                        "maxKingLevel": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("maxKingLevel", value);
                        },
                        "charmMaxNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("charmMaxNum", value);
                        },
                        "moreMissileMaxNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("moreMissileMaxNum", value);
                        },
                        "skillGiftNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("skillGiftNum", value);
                        },
                        "maxFlyHigh": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("maxFlyHigh", value);
                        },
                        "maxFallHigh": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("maxFallHigh", value);
                        },
                        "glidingTime": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("glidingTime", value);
                        },
                        "blackMarketMaxNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("blackMarketMaxNum", value);
                        },
                        "lotteryCoin": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("lotteryCoin", value);
                        },
                        "lotteryAllOrangeNum": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("lotteryAllOrangeNum", value);
                        },
                        "dieFly": function(text:String, value:Number):String
                        {
                            return this.changePlayerCount("dieFly", value);
                        },
                        "changePlayerCount": function(attr:String, value:Number):String
                        {
                            Gaming.PG.save.getCount()[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        }
                    }, "money": {
                        "coin": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_coin("coin", value);
                        },
                        "money": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_pay("money", value);
                        },
                        "totalRecharged": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_pay("totalRecharged", value);
                        },
                        "anniCoin": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_coin("anniCoin", value);
                        },
                        "tenCoin": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_coin("tenCoin", value);
                        },
                        "partsC": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_coin("partsC", value);
                        },
                        "guihua25": function(text:String, value:Number):String
                        {
                            return this.changeMainObj_coin("guihua25", value);
                        },
                        "changeMainObj_coin": function(attr:String, value:Number):String
                        {
                            Gaming.PG.save.main[attr] = value;
                            Gaming.uiGroup.mainUI.fleshCoin();
                            return "设置[" + attr + "]:" + value;
                        },
                        "changeMainObj_pay": function(attr:String, value:Number):String
                        {
                            Gaming.PG.da.main[attr] = value;
                            PayCtrl.getBalance();
                            return "设置[" + attr + "]:" + value;
                        }
                    }, "save": {
                        "readSave": function(text:String, value:Number):String
                        {
                            var ui:Array = text.split(",");
                            var uid:String = ui[0];
                            var index:int = clamp(ui[1], 0, 7);
                            Gaming.api.top.getUserData(uid, index, this.getSaveByUserData, this.getSaveError);
                            return "载入指定存档:" + uid + "_" + index;
                        },
                        "closeZuobiPanB": function(text:String, value:Number):String
                        {
                            Gaming.testCtrl.cheating.closeZuobiPanB = !Gaming.testCtrl.cheating.closeZuobiPanB;
                            return (Gaming.testCtrl.cheating.closeZuobiPanB ? "关闭" : "开启") + "作弊判断";
                        },
                        "zuobiReason": function(text:String, value:Number):String
                        {
                            var zuobiReason:String = UIOrder.zuobiPan(false, false) ? Gaming.PG.save.main.zuobiReason : "无";
                            return "作弊原因:" + zuobiReason;
                        },
                        "create_time": function(text:String, value:Number):String
                        {
                            return this.changeLoginDataObj("create_time", text);
                        },
                        "update_times": function(text:String, value:Number):String
                        {
                            return this.changeLoginDataObj("update_times", value);
                        },
                        "uidMd5": function(text:String, value:Number):String
                        {
                            var loginData:* = Gaming.PG.loginData;
                            var newMd5:String = MD5.hash(loginData.uid + "_" + loginData.save.index);
                            Gaming.PG.save.main.uidMd5 = newMd5;
                            return "过存档MD5检测";
                        },
                        "get4399Save": function(text:String, value:Number):String
                        {
                            copy(ObjectToXml.decode4399Two(Gaming.PG.save.getCopyObj()));
                            return "复制XML存档数据";
                        },
                        "getSaveData": function(text:String, value:Number):String
                        {
                            copy(JSON2.encode(Gaming.PG.save.getCopyObj()));
                            return "复制JSON存档数据";
                        },
                        "getSaveByUserData": function(userData:*):void
                        {
                            var saveObj:Object = JSON2.decode(JSON2.encode(userData.data));
                            Gaming.uiGroup.loginUI.outLoginEvent();
                            Gaming.PG.loginData.newSave(0);
                            Gaming.uiGroup.loginUI.yes_read(saveObj);
                        },
                        "getSaveError": function():void
                        {
                            Gaming.uiGroup.alertBox.showError("未找到指定存档");
                        },
                        "changeLoginDataObj": function(attr:String, value:*):String
                        {
                            Gaming.PG.loginData.save[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        }
                    }, "skill": {
                        "study": function(text:String, value:Number):String
                        {
                            var skillDef:* = Gaming.defineGroup.skill.getHeroDefineByCn(text);
                            if (skillDef && skillDef.father == "heroSkill") {
                                Gaming.PG.DATA.skillBag.addSkillByLabel(skillDef.baseLabel, skillDef.mustLv);
                                fleshUIBox("skillUI", "study");
                                Gaming.uiGroup.skillUI.wearBox.fleshData();
                                return "学习指定技能:" + text;
                            }
                            return "未找到技能:" + text;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeSkillObj("remove");
                        },
                        "lv": function(text:String, value:Number):String
                        {
                            return this.changeSkillObj("lv", value);
                        },
                        "dayProfi": function(text:String, value:Number):String
                        {
                            return this.changeSkillObj("dayProfi", value);
                        },
                        "profi": function(text:String, value:Number):String
                        {
                            return this.changeSkillObj("profi", value);
                        },
                        "changeSkillObj": function(attr:String, value:* = null):String
                        {
                            var skillData:* = Gaming.uiGroup.skillUI.upgradeBox.nowData;
                            if (skillData) {
                                var tipText:String = "";
                                var skillSave:* = skillData.save;
                                if (attr == "remove") {
                                    var skillDef:* = skillSave.getDefine();
                                    skillData.heroSkillDataGroup.removeData(skillData);
                                    tipText = "删除:" + skillDef.cnName;
                                } else {
                                    if (attr == "lv") {
                                        var skillMaxLv:int = skillSave.getOriginalDefine().getMaxLevel();
                                        value = clamp(value, 1, skillMaxLv);
                                    }
                                    skillSave[attr] = value;
                                    tipText = "设置[" + attr + "]:" + value;
                                }
                                fleshUIBox("skillUI", "upgrade");
                                Gaming.uiGroup.skillUI.wearBox.fleshData();
                                return tipText;
                            }
                            return "未找到技能([技能][升级])";
                        }
                    }, "space": {
                        "diff": function(text:String, value:Number):String
                        {
                            return this.changeSpaceMapCount(text, "diff", value);
                        },
                        "win": function(text:String, value:Number):String
                        {
                            return this.changeSpaceMapCount(text, "win", value);
                        },
                        "exp": function(text:String, value:Number):String
                        {
                            return this.changeSpaceMapCount(text, "exp", value);
                        },
                        "shieldKill": function(text:String, value:Number):String
                        {
                            return this.changeSpaceCount("shieldKill", value);
                        },
                        "screenKill": function(text:String, value:Number):String
                        {
                            return this.changeSpaceCount("screenKill", value);
                        },
                        "screenKillB": function(text:String, value:Number):String
                        {
                            return this.changeSpaceCount("screenKillB", value);
                        },
                        "setLevel": function(text:String, value:Number):String
                        {
                            return this.changeCraftObj("setLevel", value);
                        },
                        "addExp": function(text:String, value:Number):String
                        {
                            return this.changeCraftObj("addExp", value);
                        },
                        "setPoint": function(text:String, value:Number):String
                        {
                            return this.changeCraftObj("setPoint", value, text);
                        },
                        "changeSpaceMapCount": function(map:String, attr:String, value:Number):String
                        {
                            var spaceMapDef:* = Gaming.defineGroup.worldMap.getDefineByCn(map);
                            if (spaceMapDef && spaceMapDef.father == "space") {
                                Gaming.PG.save.space.setMapPro(spaceMapDef.name, attr, value);
                                return "设置[" + attr + "]:" + value;
                            }
                            return "未找到太空地图:" + map;
                        },
                        "changeSpaceCount": function(attr:String, value:Number):String
                        {
                            Gaming.PG.save.space.c.setAttribute(attr, value);
                            return "设置[" + attr + "]:" + value;
                        },
                        "changeCraftObj": function(method:String, value:Number, skill:String = ""):String
                        {
                            var craftData:* = Gaming.PG.da.space.getNowCraft();
                            if (craftData) {
                                if (method == "setPoint") {
                                    var pointDef:* = null;
                                    var pointArr:Array = craftData.getPointDefArr();
                                    for each (pointDef in pointArr) {
                                        if (pointDef.getSkillDefine().cnName == skill) {
                                            var point:String = pointDef.skill;
                                            craftData.setPoint(point, value);
                                            return "设置[" + point + "]:" + value;
                                        }
                                    }
                                    return "未找到飞船技能:" + skill;
                                }
                                craftData[method](value);
                                return "调用[" + method + "]:" + value;
                            }
                            return "未找到飞船";
                        }
                    }, "food": {
                        "addRaw": function(text:String, value:Number):String
                        {
                            var foodName:String = this.getName_food("raw", text);
                            if (foodName) {
                                Gaming.PG.da.food.addRawNum(foodName, value);
                                return "添加" + text + ":" + value;
                            }
                            return "未找到食材:" + text;
                        },
                        "addBook": function(text:String, value:Number):String
                        {
                            var foodName:String = this.getName_food("book", text);
                            if (foodName) {
                                Gaming.PG.save.food.bookObj.addNum(foodName, value);
                                return "添加" + text + ":" + value;
                            }
                            return "未找到美食:" + text;
                        },
                        "addRawAll": function(text:String, value:Number):String
                        {
                            Gaming.PG.da.food.addRawAll(value);
                            return "添加所有食材:" + value;
                        },
                        "profiAll": function(text:String, value:Number):String
                        {
                            return this.changeFoodObj("profiAll", value);
                        },
                        "eat": function(text:String, value:Number):String
                        {
                            var foodName:String = this.getName_food("book", text);
                            if (foodName) {
                                this.changeFoodObj("eatName", foodName);
                                this.changeFoodObj("eatTime", 300);
                                this.changeFoodObj("eatNameArr", foodName, "push", true);
                                return "食用美食:" + text;
                            }
                            return "未找到美食:" + text;
                        },
                        "clear_eat": function(text:String, value:Number):String
                        {
                            this.changeFoodObj("eatName", "");
                            this.changeFoodObj("eatTime", 0);
                            this.changeFoodObj("eatNameArr", []);
                            this.changeFoodObj("eatNum", 0);
                            return "取消今日进食";
                        },
                        "eatTime": function(text:String, value:Number):String
                        {
                            return this.changeFoodObj("eatTime", value);
                        },
                        "eatNum": function(text:String, value:Number):String
                        {
                            return this.changeFoodObj("eatNum", value);
                        },
                        "dropAll": function(text:String, value:Number):String
                        {
                            return this.changeFoodObj("dropAll", value);
                        },
                        "eatAll": function(text:String, value:Number):String
                        {
                            return this.changeFoodObj("eatAll", value);
                        },
                        "getName_food": function(type:String, cnName:String):String
                        {
                            var foodDef:* = null;
                            var foodDefArr:Array = Gaming.defineGroup.food[type].arr;
                            for each (foodDef in foodDefArr) {
                                if (foodDef.getCnName() == cnName) {
                                    return foodDef.getName();
                                }
                            }
                            return "";
                        },
                        "changeFoodObj": function(attr:String, value:*, method:String = "", isMethod:Boolean = false):String
                        {
                            var foodSave:* = Gaming.PG.save.food;
                            if (isMethod) {
                                foodSave[attr][method](value);
                                return "调用[" + method + "]:" + value;
                            }
                            foodSave[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        }
                    }, "bossCard": {
                        "add": function(text:String, value:Number):String
                        {
                            var bodyDef:* = Gaming.defineGroup.body.getCnDefine(text);
                            if (bodyDef) {
                                var bcardStarMax:int = BossCardCreator.getStarMax();
                                var bcardStar:int = clamp(value, 1, bcardStarMax);
                                var bcardSave:* = BossCardCreator.getSaveStar(bcardStar, [], bodyDef.name);
                                Gaming.PG.da.bossCard.addSave(bcardSave);
                                Gaming.uiGroup.bosseditUI.fleshCardBox();
                                return "添加魂卡:" + text;
                            }
                            return "未找到实体:" + text;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("remove");
                        },
                        "n": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("n", text);
                        },
                        "s": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("s", value);
                        },
                        "li": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("li", value);
                        },
                        "dp": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("dp", value);
                        },
                        "lk": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("lk", Number(Boolean(value)));
                        },
                        "o": function(text:String, value:Number):String
                        {
                            var pro:String = getProByCn(text);
                            if (pro) {
                                return this.changeBossCardObj(pro, value, "o");
                            }
                            return "未找到魂卡属性:" + text;
                        },
                        "addSkill": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("addSkill", getSkillByCn(text), "sr");
                        },
                        "deleteSkill": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("deleteSkill", getSkillByCn(text), "sr");
                        },
                        "sr": function(text:String, value:Number):String
                        {
                            return this.changeBossCardObj("sr", getSkillArrByCnArr(text.split(",")));
                        },
                        "num": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("num", value);
                        },
                        "hNum": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("hNum", value);
                        },
                        "s7N": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("s7N", value);
                        },
                        "t": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("t", Number(1200 - value));
                        },
                        "v": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("v", value);
                        },
                        "demV": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("demV", value);
                        },
                        "autoDown": function(text:String, value:Number):String
                        {
                            var autoDownStatus:Boolean = !Gaming.PG.save.bossCard.autoDown;
                            return this.changeBossCardCount("autoDown", autoDownStatus);
                        },
                        "pkWin": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("pkWin", value);
                        },
                        "pkWinStar": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("pkWinStar", value);
                        },
                        "pkStone": function(text:String, value:Number):String
                        {
                            return this.changeBossCardCount("pkStone", value);
                        },
                        "changeBossCardCount": function(attr:String, value:*):String
                        {
                            Gaming.PG.save.bossCard[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        },
                        "changeBossCardObj": function(attr:String, value:* = null, type:String = ""):String
                        {
                            var isValid:Boolean = false;
                            var bcardSave:* = null;
                            var bcardSaveArr:Array = Gaming.PG.save.bossCard.arr;
                            for each (bcardSave in bcardSaveArr) {
                                if (Boolean(bcardSave.lk)) {
                                    isValid = true;
                                    break;
                                }
                            }
                            if (isValid) {
                                var tipText:String = "";
                                if (attr == "remove") {
                                    var bcardData:* = null;
                                    var bcardDataArr:Array = Gaming.PG.da.bossCard.getDataArr();
                                    tipText = "已删除";
                                    for each (bcardData in bcardDataArr) {
                                        if (bcardData.getCardSave() == bcardSave) {
                                            Gaming.PG.da.bossCard.removeData(bcardData);
                                            tipText = "删除:" + Gaming.defineGroup.body.nameToCn(bcardSave.n);
                                        }
                                    }
                                } else if (attr == "addSkill") {
                                    bcardSave[type].push(value);
                                    tipText = "添加魂卡技能:" + value;
                                } else if (attr == "deleteSkill") {
                                    var bcardSkillArr:Array = bcardSave[type];
                                    var bcardSkillIdx:int = bcardSkillArr.indexOf(value);
                                    tipText = "未找到魂卡技能:" + value;
                                    if (bcardSkillIdx >= 0) {
                                        bcardSkillArr.splice(bcardSkillIdx, 1);
                                        bcardSave[type] = bcardSkillArr;
                                        tipText = "删除魂卡技能:" + value;
                                    }
                                } else {
                                    if (type) {
                                        var bcardProObj:Object = bcardSave[type];
                                        bcardProObj[attr] = value;
                                        bcardSave[type] = bcardProObj;
                                        tipText = "设置[" + type + "][" + attr + "]:" + value;
                                    } else {
                                        bcardSave[attr] = value;
                                        if (typeof value == "object") {
                                            tipText = "设置[" + attr + "]:" + value.length + "个";
                                        } else {
                                            tipText = "设置[" + attr + "]:" + value;
                                        }
                                    }
                                }
                                Gaming.uiGroup.bosseditUI.fleshCardBox();
                                return tipText;
                            }
                            return "未找到魂卡([背包][锁住])";
                        }
                    }, "task": {
                        "unlockAllByType": function(text:String, value:Number):String
                        {
                            var type:String = this.getTaskLabelByCn(text);
                            if (type) {
                                Gaming.PG.da.task.unlockAllByType(type);
                                Gaming.uiGroup.taskUI.show();
                                return "解锁所有" + text + "任务";
                            }
                            return "未找到任务类型:" + text;
                        },
                        "getAllByType": function(text:String, value:Number):String
                        {
                            var type:String = this.getTaskLabelByCn(text);
                            if (type) {
                                var n:Number = 0;
                                var taskName:String = "";
                                var taskData:TaskData = null;
                                var taskDefArr:Array = Gaming.defineGroup.task.getArrByType(type);
                                for (n in taskDefArr) {
                                    taskName = taskDefArr[n].name;
                                    taskData = Gaming.PG.da.task.getTaskDataByName(taskName);
                                    if (taskData && !taskData.isIng()) {
                                        taskData.getTask();
                                    }
                                }
                                Gaming.uiGroup.taskUI.show();
                                return "接取所有" + text + "任务";
                            }
                            return "未找到任务类型:" + text;
                        },
                        "completeAllByType": function(text:String, value:Number):String
                        {
                            var type:String = this.getTaskLabelByCn(text);
                            if (type) {
                                var n:Number = 0;
                                var taskSave:* = null;
                                var taskSaveArr:Array = Gaming.PG.save.task.dataArr;
                                for each (taskSave in taskSaveArr) {
                                    var taskData:TaskData = new TaskData();
                                    taskData.inData_bySave(taskSave, Gaming.PG.da);
                                    if (taskData.def.father == type) {
                                        taskData.complete();
                                        n++;
                                    }
                                }
                                Gaming.uiGroup.taskUI.show();
                                return "完成所有" + text + "任务:" + n + "个";
                            }
                            return "未找到任务类型:" + text;
                        },
                        "getGiftAll": function(text:String, value:Number):String
                        {
                            var n:Number = 0;
                            var taskSave:* = null;
                            var taskSaveArr:Array = Gaming.PG.save.task.dataArr;
                            var bagPanText:String = "";
                            for each (taskSave in taskSaveArr) {
                                if (taskSave.state == "complete") {
                                    var taskGift:* = null;
                                    var taskData:TaskData = new TaskData();
                                    taskData.inData_bySave(taskSave, Gaming.PG.da);
                                    taskGift = taskData.getGift();
                                    bagPanText = GiftAddit.bagSpacePan(taskGift);
                                    if (bagPanText) {
                                        Gaming.uiGroup.alertBox.showNormal(bagPanText, "no", null, null, "no");
                                        break;
                                    }
                                    taskData.getTaskGift();
                                    GiftAddit.add(taskGift);
                                    n++;
                                }
                            }
                            UIShow.flesh_coinChange();
                            Gaming.uiGroup.mainUI.fleshBtn();
                            Gaming.uiGroup.moreBox.fleshData();
                            Gaming.uiGroup.worldMapBox.fleshData();
                            Gaming.uiGroup.taskUI.show();
                            return "领取已完成任务奖励:" + n + "次";
                        },
                        "getTaskLabelByCn": function(cnName:String):String
                        {
                            var n:Number = 0;
                            var labelArr:Array = TaskType.labelArr;
                            var labelCnArr:Array = TaskType.labelCnArr;
                            for (n in labelCnArr) {
                                if (labelCnArr[n] == cnName) {
                                    return labelArr[n];
                                }
                            }
                            return "";
                        }
                    }, "buff": {
                        "addBuff": function(text:String, value:Number):String
                        {
                            var thingsDef:* = Gaming.defineGroup.things.getDefineByCnName(text);
                            if (thingsDef) {
                                if (thingsDef.stateD != null) {
                                    Gaming.PG.SAVE.state.addByDefine(thingsDef.stateD);
                                    return "使用增益道具:" + text;
                                }
                            }
                            return "未找到物品(增益道具):" + text;
                        },
                        "doubleExpTime": function(text:String, value:Number):String
                        {
                            return this.changeTimeObj("doubleExpTime", value);
                        },
                        "doubleMaterialsDropTime": function(text:String, value:Number):String
                        {
                            return this.changeTimeObj("doubleMaterialsDropTime", value);
                        },
                        "doubleArmsDropTime": function(text:String, value:Number):String
                        {
                            return this.changeTimeObj("doubleArmsDropTime", value);
                        },
                        "doubleEquipDropTime": function(text:String, value:Number):String
                        {
                            return this.changeTimeObj("doubleEquipDropTime", value);
                        },
                        "clearAllTime": function(text:String, value:Number):String
                        {
                            Gaming.PG.SAVE.time.clearAllTime();
                            return "清除所有双倍时间";
                        },
                        "changeTimeObj": function(attr:String, value:Number):String
                        {
                            Gaming.PG.SAVE.time[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        }
                    }, "pet": {
                        "add": function(text:String, value:Number):String
                        {
                            var geneDef:* = Gaming.defineGroup.gene.getDefineByCn(text);
                            if (geneDef) {
                                var geneData:* = Gaming.defineGroup.geneCreator.getTempSuperData(geneDef.name);
                                Gaming.PG.da.pet.addByGeneData(geneData);
                                return "添加尸宠:" + text;
                            }
                            return "找不到尸宠:" + text;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changePetObj("remove");
                        },
                        "playerName": function(text:String, value:Number):String
                        {
                            return this.changePetObj("base", "playerName", text);
                        },
                        "level": function(text:String, value:Number):String
                        {
                            return this.changePetObj("base", "level", value);
                        },
                        "exp": function(text:String, value:Number):String
                        {
                            return this.changePetObj("base", "exp", value);
                        },
                        "color": function(text:String, value:Number):String
                        {
                            return this.changePetObj("gene", "color", toColor(text));
                        },
                        "dpsAdd": function(text:String, value:Number):String
                        {
                            return this.changePetObj("base", "dpsAdd", value);
                        },
                        "lifeAdd": function(text:String, value:Number):String
                        {
                            return this.changePetObj("base", "lifeAdd", value);
                        },
                        "headAdd": function(text:String, value:Number):String
                        {
                            return this.changePetObj("base", "headAdd", value);
                        },
                        "fightB": function(text:String, value:Number):String
                        {
                            return this.changePetObj("", "fightB");
                        },
                        "suppleB": function(text:String, value:Number):String
                        {
                            return this.changePetObj("", "suppleB");
                        },
                        "obj": function(text:String, value:Number):String
                        {
                            return this.changePetGrowObj(text, value);
                        },
                        "growObj": function(text:String, value:Number):String
                        {
                            return this.changePetGrowObj(text, value, true);
                        },
                        "study": function(text:String, value:Number):String
                        {
                            return this.changePetSkillObj(text);
                        },
                        "skillLv": function(text:String, value:Number):String
                        {
                            return this.changePetSkillObj(text, value);
                        },
                        "limitDps": function(text:String, value:Number):String
                        {
                            var petData:* = PetUI.getNowData();
                            if (petData) {
                                var petStrengthenProDefGroup:* = Gaming.defineGroup.gene.strengthenPro;
                                var dpsProDef:* = petStrengthenProDefGroup.getDefine("dps");
                                var lifeProDef:* = petStrengthenProDefGroup.getDefine("life");
                                var headProDef:* = petStrengthenProDefGroup.getDefine("head");
                                var dpsProMaxLv:int = int(dpsProDef.getDataLen() - 1);
                                var lifeProMaxLv:int = int(lifeProDef.getDataLen() - 1);
                                var headProMaxLv:int = int(headProDef.getDataLen() - 1);
                                this.changePetObj("base", "level", PlayerBaseData.MAX_LEVEL);
                                this.changePetObj("base", "dpsAdd", dpsProMaxLv);
                                this.changePetObj("base", "lifeAdd", lifeProMaxLv);
                                this.changePetObj("base", "headAdd", headProMaxLv);
                                this.changePetObj("gene", "color", "orange");
                                this.changePetGrowObj("战斗力", 0.46);
                                this.changePetGrowObj("伤害", 0.46);
                                this.changePetGrowObj("生命", 0);
                                this.changePetGrowObj("头部防御", 0);
                                this.changePetGrowObj("生命回复", 7033);
                                this.changePetGrowObj("3倍暴击", 0.23);
                                this.changePetGrowObj("技能回速", 0);
                                this.changePetGrowObj("闪避", 0.32);
                                this.changePetGrowObj("近伤减免", 0.55);
                                this.changePetGrowObj("移动速度", 0.32);
                                this.changePetGrowObj("战斗力", 0.54, true);
                                this.changePetGrowObj("伤害", 0.54, true);
                                this.changePetGrowObj("生命", 0.12, true);
                                this.changePetGrowObj("头部防御", 0, true);
                                this.changePetGrowObj("生命回复", 0.4, true);
                                this.changePetGrowObj("3倍暴击", 0.25, true);
                                this.changePetGrowObj("技能回速", 0.25, true);
                                this.changePetGrowObj("闪避", 0.2, true);
                                this.changePetGrowObj("近伤减免", 0.25, true);
                                this.changePetGrowObj("移动速度", 0.25, true);
                                return "设置极限战力属性:" + petData.getCnName();
                            }
                            return "未找到尸宠([背包])";
                        },
                        "changePetObj": function(type:String, attr:String = "", value:* = null):String
                        {
                            var petData:* = PetUI.getNowData();
                            if (petData) {
                                var tipText:String = "";
                                var petSave:* = petData.save;
                                if (type == "remove") {
                                    var petDataArr:Array = Gaming.PG.da.pet.arr;
                                    var petDataIdx:int = petDataArr.indexOf(petData);
                                    tipText = "已删除";
                                    if (petDataIdx >= 0) {
                                        petDataArr.splice(petDataIdx, 1);
                                        Gaming.PG.da.pet.fleshSaveGroup();
                                        tipText = "删除:" + petData.getCnName();
                                    }
                                } else {
                                    if (type) {
                                        petData[type].save[attr] = value;
                                        tipText = "设置[" + type + "][" + attr + "]:" + value;
                                    } else {
                                        var statusValue:Boolean = !petSave[attr];
                                        petSave[attr] = statusValue;
                                        tipText = "设置[" + attr + "]:" + statusValue;
                                    }
                                }
                                Gaming.uiGroup.petUI.fleshData();
                                return tipText;
                            }
                            return "未找到尸宠([背包])";
                        },
                        "changePetGrowObj": function(text:String, value:Number, isGrow:Boolean = false):String
                        {
                            var petData:* = PetUI.getNowData();
                            if (petData) {
                                var pro:String = getPetProByCn(text);
                                if (pro) {
                                    var attr:String = isGrow ? "growObj" : "obj";
                                    var petProObj:Object = petData.gene.save[attr];
                                    petProObj[pro] = value;
                                    petData.gene.save[attr] = petProObj;
                                    petData.fleshProData();
                                    Gaming.uiGroup.petUI.fleshData();
                                    return "设置[" + attr + "][" + pro + "]:" + value;
                                }
                                return "未找到尸宠属性:" + text;
                            }
                            return "未找到尸宠([背包])";
                        },
                        "changePetSkillObj": function(skill:String, value:* = null):String
                        {
                            var petData:* = PetUI.getNowData();
                            if (petData) {
                                var tipText:String = "未找到尸宠技能:" + skill;
                                var petSave:* = petData.save;
                                var petSkillDef:* = getPetStudySkillDefByCn(petData, skill);
                                if (petSkillDef) {
                                    if (value) {
                                        var petSkill:* = null;
                                        var petSkillArr:Array = petSave.skill.arr;
                                        for each (petSkill in petSkillArr) {
                                            if (petSkill.baseLabel == petSkillDef.baseLabel) {
                                                var petSkillMaxLv:int = petSkill.getOriginalDefine().getMaxLevel();
                                                value = clamp(value, 1, petSkillMaxLv);
                                                petSkill.lv = value;
                                                tipText = "设置" + skill + ":" + value;
                                            }
                                        }
                                    } else {
                                        petData.skill.addSkillByLabel(petSkillDef.baseLabel, petSkillDef.mustLv);
                                        tipText = "学习指定尸宠技能:" + skill;
                                    }
                                }
                                Gaming.uiGroup.petUI.fleshData();
                                return tipText;
                            }
                            return "未找到尸宠([背包])";
                        }
                    }, "arms": {
                        "add": function(text:String, value:Number):String
                        {
                            var nc:Array = text.split(",");
                            var armsCnName:String = nc[0];
                            var armsColor:String = toColor(nc[1]);
                            var armsRangeDef:* = getArmsRangeDefByCn(armsCnName);
                            if (armsRangeDef) {
                                var armsName:String = armsRangeDef.def.name;
                                var armsSave:* = Gaming.defineGroup.armsCreator.getSuperSaveByArmsRangeName(Gaming.PG.da.level, armsName);
                                armsSave.color = armsColor;
                                Gaming.PG.da.armsBag.addSave(armsSave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加武器:" + armsCnName;
                            }
                            return "未找到武器:" + armsCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("remove");
                        },
                        "cnName": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("cnName", text);
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("name", text);
                        },
                        "color": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("color", toColor(text));
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("strengthenLv", value);
                        },
                        "evoLv": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("evoLv", value);
                        },
                        "ele": function(text:String, value:Number):String
                        {
                            var eleHurt:String = getArmsElementHurtByCn(text);
                            if (eleHurt) {
                                return this.changeArmsObj("ele", eleHurt);
                            }
                            return "未找到武器元素伤害类型:" + text;
                        },
                        "eleLv": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("eleLv", value);
                        },
                        "critD_mul": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("mul", value, "critD");
                        },
                        "critD_pro": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("pro", value, "critD");
                        },
                        "hurtRatio": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("hurtRatio", value);
                        },
                        "capacity": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("capacity", value);
                        },
                        "reloadGap": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("reloadGap", value);
                        },
                        "attackGap": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("attackGap", value);
                        },
                        "bulletNum": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("bulletNum", value);
                        },
                        "shootAngle": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("shootAngle", value);
                        },
                        "shakeAngle": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("shakeAngle", value);
                        },
                        "twoShootPro": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("twoShootPro", value);
                        },
                        "armsImgLabel": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("armsImgLabel", text);
                        },
                        "shootSoundUrl": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("shootSoundUrl", text);
                        },
                        "bulletWidth": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("bulletWidth", value);
                        },
                        "bulletShakeWidth": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("bulletShakeWidth", value);
                        },
                        "followD_value": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("value", value, "followD");
                        },
                        "followD_delay": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("delay", value, "followD");
                        },
                        "followD_maxTime": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("maxTime", value, "followD");
                        },
                        "followD_hitIsTargetB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("hitIsTargetB", Boolean(value), "followD");
                        },
                        "penetrationNum": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("penetrationNum", value);
                        },
                        "penetrationGap": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("penetrationGap", value);
                        },
                        "bounceD_floor": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("floor", value, "bounceD");
                        },
                        "bounceD_body": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("body", value, "bounceD");
                        },
                        "bounceD_vMul": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("vMul", value, "bounceD");
                        },
                        "bounceD_liveInitB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("liveInitB", Boolean(value), "bounceD");
                        },
                        "bounceD_glueFloorB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("glueFloorB", Boolean(value), "bounceD");
                        },
                        "bounceD_hurtNumAdd": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("hurtNumAdd", value, "bounceD");
                        },
                        "bounceD_noHitTime": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("noHitTime", value, "bounceD");
                        },
                        "bounceD_noDieB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("noDieB", Boolean(value), "bounceD");
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("lockB", Boolean(value));
                        },
                        "firstChoiceB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("firstChoiceB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("evo");
                        },
                        "strengthen": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("strengthen");
                        },
                        "evoMax": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("evoMax");
                        },
                        "strengthenMax": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("strengthenMax");
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeArmsObj("getTime", text) + "\n";
                            tipText += this.changeArmsObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("inHouseTime", text);
                        },
                        "addSkill": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("addSkill", getSkillByCn(text), "skillArr");
                        },
                        "deleteSkill": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("deleteSkill", getSkillByCn(text), "skillArr");
                        },
                        "skillArr": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("skillArr", getSkillArrByCnArr(text.split(",")));
                        },
                        "addGodSkill": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("addSkill", getSkillByCn(text), "godSkillArr");
                        },
                        "deleteGodSkill": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("deleteSkill", getSkillByCn(text), "godSkillArr");
                        },
                        "godSkillArr": function(text:String, value:Number):String
                        {
                            return this.changeArmsObj("godSkillArr", getSkillArrByCnArr(text.split(",")));
                        },
                        "changeArmsObj": function(attr:String, value:* = null, type:String = ""):String
                        {
                            var armsData:* = Gaming.uiGroup.forgingUI.armsUpgradeBoard.nowData;
                            if (armsData) {
                                var n:Number = 0;
                                var tipText:String = "";
                                var armsSave:* = armsData.save;
                                if (attr == "addSkill") {
                                    armsSave[type].push(value);
                                    tipText = "添加武器技能:" + value;
                                } else if (attr == "deleteSkill") {
                                    var armsSkillArr:Array = armsSave[type];
                                    var armsSkillIdx:int = armsSkillArr.indexOf(value);
                                    tipText = "未找到武器技能:" + value;
                                    if (armsSkillIdx >= 0) {
                                        armsSkillArr.splice(armsSkillIdx, 1);
                                        armsSave[type] = armsSkillArr;
                                        tipText = "删除武器技能:" + value;
                                    }
                                } else if (attr == "evo") {
                                    if (armsData.canEvoB()) {
                                        ArmsEvoCtrl.evo(armsData);
                                        tipText = "进阶武器";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "evoMax") {
                                    while (armsData.canEvoB()) {
                                        ArmsEvoCtrl.evo(armsData);
                                        n++;
                                    }
                                    tipText = "已进阶至最高等级,累计进阶:" + n + "次";
                                } else if (attr == "strengthen") {
                                    if (!isMaxStrengthenLv(armsSave, ArmsStrengthenCtrl)) {
                                        ArmsStrengthenCtrl.strengthenOne(armsData, true);
                                        tipText = "强化武器";
                                    } else {
                                        tipText = "已强化至最高等级";
                                    }
                                } else if (attr == "strengthenMax") {
                                    while (!isMaxStrengthenLv(armsSave, ArmsStrengthenCtrl)) {
                                        ArmsStrengthenCtrl.strengthenOne(armsData, true);
                                        n++;
                                    }
                                    tipText = "已强化至最高等级,累计强化:" + n + "次";
                                } else if (attr == "remove") {
                                    armsData.fatherData.removeData(armsData);
                                    tipText = "删除:" + armsData.getCnName();
                                } else {
                                    if (type) {
                                        armsSave[type][attr] = value;
                                        tipText = "设置[" + type + "][" + attr + "]:" + value;
                                    } else {
                                        armsSave[attr] = value;
                                        if (typeof value == "object") {
                                            tipText = "设置[" + attr + "]:" + value.length + "个";
                                        } else {
                                            tipText = "设置[" + attr + "]:" + value;
                                        }
                                    }
                                }
                                fleshUIBox("forgingUI", "armsUpgrade");
                                Gaming.uiGroup.allBagUI.fleshAllBox();
                                return tipText;
                            }
                            return "未找到武器([锻造][武器][升级])";
                        }
                    }, "equip": {
                        "add": function(text:String, value:Number):String
                        {
                            var nc:Array = text.split(",");
                            var equipCnName:String = nc[0];
                            var equipColor:String = toColor(nc[1]);
                            var equipDef:* = getEquipDefByCn(equipCnName);
                            if (equipDef) {
                                var equipCreator:* = Gaming.defineGroup.equipCreator;
                                var equipLv:int = Gaming.PG.da.level;
                                var equipName:String = equipDef.name;
                                var equipSave:* = null;
                                if (equipDef.isDarkgoldAndMoreB()) {
                                    equipSave = equipCreator.getDarkgoldSave(equipName);
                                } else if (equipDef.isBlack90()) {
                                    equipSave = equipCreator.getBlackSave(equipLv, equipName, true);
                                } else {
                                    equipSave = equipCreator.getSuperSave("red", equipLv, equipName, true);
                                }
                                equipSave.cnName = equipCnName;
                                equipSave.imgName = equipName;
                                equipSave.color = equipColor;
                                equipSave.itemsLevel = equipLv;
                                equipSave.obj = equipSave.getTrueObj();
                                Gaming.PG.da.equipBag.addSave(equipSave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加装备:" + equipCnName;
                            }
                            return "未找到装备:" + equipCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("imgName", text);
                        },
                        "color": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("color", toColor(text));
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("strengthenLv", value);
                        },
                        "partType": function(text:String, value:Number):String
                        {
                            var equipType:String = getEquipPartTypeByCn(text);
                            if (equipType) {
                                return this.changeEquipObj("partType", equipType);
                            }
                            return "未找到装备类型:" + text;
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("evo");
                        },
                        "strengthen": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("strengthen");
                        },
                        "evoMax": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("evoMax");
                        },
                        "strengthenMax": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("strengthenMax");
                        },
                        "obj": function(text:String, value:Number):String
                        {
                            var pro:String = getProByCn(text);
                            if (pro) {
                                return this.changeEquipObj(pro, value, "obj");
                            }
                            return "未找到装备属性:" + text;
                        },
                        "heroSkillAddObj": function(text:String, value:Number):String
                        {
                            var heroSkillDef:* = Gaming.defineGroup.skill.getHeroDefineByCn(text);
                            if (heroSkillDef) {
                                return this.changeEquipObj(heroSkillDef.baseLabel, value, "heroSkillAddObj");
                            }
                            return "未找到装备技能附加属性:" + text;
                        },
                        "addSkill": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("addSkill", getSkillByCn(text), "skillArr");
                        },
                        "deleteSkill": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("deleteSkill", getSkillByCn(text), "skillArr");
                        },
                        "skillArr": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("skillArr", getSkillArrByCnArr(text.split(",")));
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeEquipObj("getTime", text) + "\n";
                            tipText += this.changeEquipObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeEquipObj("inHouseTime", text);
                        },
                        "changeEquipObj": function(attr:String, value:* = null, type:String = ""):String
                        {
                            var equipData:* = Gaming.uiGroup.forgingUI.equipUpgradeBoard.nowData;
                            if (equipData) {
                                var n:Number = 0;
                                var tipText:String = "";
                                var equipSave:* = equipData.save;
                                if (attr == "addSkill") {
                                    equipSave[type].push(value);
                                    tipText = "添加装备技能:" + value;
                                } else if (attr == "deleteSkill") {
                                    var equipSkillArr:Array = equipSave[type];
                                    var equipSkillIdx:int = equipSkillArr.indexOf(value);
                                    tipText = "未找到装备技能:" + value;
                                    if (equipSkillIdx >= 0) {
                                        equipSkillArr.splice(equipSkillIdx, 1);
                                        equipSave[type] = equipSkillArr;
                                        tipText = "删除装备技能:" + value;
                                    }
                                } else if (attr == "evo") {
                                    if (equipData.canEvoB()) {
                                        EquipEvoCtrl.evo(equipData);
                                        tipText = "进阶装备";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "evoMax") {
                                    while (equipData.canEvoB()) {
                                        EquipEvoCtrl.evo(equipData);
                                        n++;
                                    }
                                    tipText = "已进阶至最高等级,累计进阶:" + n + "次";
                                } else if (attr == "strengthen") {
                                    if (!isMaxStrengthenLv(equipSave, EquipStrengthenCtrl)) {
                                        EquipStrengthenCtrl.strengthenOne(equipData, true);
                                        tipText = "强化装备";
                                    } else {
                                        tipText = "已强化至最高等级";
                                    }
                                } else if (attr == "strengthenMax") {
                                    while (!isMaxStrengthenLv(equipSave, EquipStrengthenCtrl)) {
                                        EquipStrengthenCtrl.strengthenOne(equipData, true);
                                        n++;
                                    }
                                    tipText = "已强化至最高等级,累计强化:" + n + "次";
                                } else if (attr == "remove") {
                                    equipData.getFatherData().removeData(equipData);
                                    tipText = "删除:" + equipData.getCnName();
                                } else {
                                    if (type) {
                                        var equipProObj:Object = equipSave[type];
                                        equipProObj[attr] = value;
                                        equipSave[type] = equipProObj;
                                        tipText = "设置[" + type + "][" + attr + "]:" + value;
                                    } else {
                                        equipSave[attr] = value;
                                        if (typeof value == "object") {
                                            tipText = "设置[" + attr + "]:" + value.length + "个";
                                        } else {
                                            tipText = "设置[" + attr + "]:" + value;
                                        }
                                    }
                                }
                                fleshUIBox("forgingUI", "equipUpgrade");
                                Gaming.uiGroup.allBagUI.fleshAllBox();
                                return tipText;
                            }
                            return "未找到装备([锻造][装备][升级])";
                        }
                    }, "fashion": {
                        "add": function(text:String, value:Number):String
                        {
                            var fashionDef:* = Gaming.defineGroup.equip.getFashionDefineByCn(text);
                            if (fashionDef) {
                                var fashionSave:* = Gaming.defineGroup.equipCreator.getFashionSave(fashionDef.name);
                                Gaming.PG.da.equipBag.addSave(fashionSave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加时装:" + text;
                            }
                            return "未找到时装:" + text;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("imgName", text);
                        },
                        "color": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("color", toColor(text));
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("strengthenLv", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("newB", Boolean(value));
                        },
                        "obj": function(text:String, value:Number):String
                        {
                            var pro:String = getProByCn(text);
                            if (pro) {
                                return this.changeFashionObj(pro, value, "obj");
                            }
                            return "未找到时装属性:" + text;
                        },
                        "heroSkillAddObj": function(text:String, value:Number):String
                        {
                            var heroSkillDef:* = Gaming.defineGroup.skill.getHeroDefineByCn(text);
                            if (heroSkillDef) {
                                return this.changeFashionObj(heroSkillDef.baseLabel, value, "heroSkillAddObj");
                            }
                            return "未找到时装技能附加属性:" + text;
                        },
                        "addSkill": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("addSkill", getSkillByCn(text), "skillArr");
                        },
                        "deleteSkill": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("deleteSkill", getSkillByCn(text), "skillArr");
                        },
                        "skillArr": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("skillArr", getSkillArrByCnArr(text.split(",")));
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeFashionObj("getTime", text) + "\n";
                            tipText += this.changeFashionObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeFashionObj("inHouseTime", text);
                        },
                        "changeFashionObj": function(attr:String, value:* = null, type:String = ""):String
                        {
                            var isValid:Boolean = false;
                            var equipSave:* = null;
                            var equipData:* = null;
                            var equipDataArr:Array = Gaming.PG.da.equipBag.dataArr;
                            for each (equipData in equipDataArr) {
                                equipSave = equipData.save;
                                if (equipSave.partType == "fashion" && equipSave.lockB) {
                                    isValid = true;
                                    break;
                                }
                            }
                            if (isValid) {
                                var tipText:String = "";
                                if (attr == "addSkill") {
                                    equipSave[type].push(value);
                                    tipText = "添加时装技能:" + value;
                                } else if (attr == "deleteSkill") {
                                    var equipSkillArr:Array = equipSave[type];
                                    var equipSkillIdx:int = equipSkillArr.indexOf(value);
                                    tipText = "未找到时装技能:" + value;
                                    if (equipSkillIdx >= 0) {
                                        equipSkillArr.splice(equipSkillIdx, 1);
                                        equipSave[type] = equipSkillArr;
                                        tipText = "删除时装技能:" + value;
                                    }
                                } else if (attr == "remove") {
                                    equipData.getFatherData().removeData(equipData);
                                    tipText = "删除:" + equipData.getCnName();
                                } else {
                                    if (type) {
                                        var equipProObj:Object = equipSave[type];
                                        equipProObj[attr] = value;
                                        equipSave[type] = equipProObj;
                                        tipText = "设置[" + type + "][" + attr + "]:" + value;
                                    } else {
                                        equipSave[attr] = value;
                                        if (typeof value == "object") {
                                            tipText = "设置[" + attr + "]:" + value.length + "个";
                                        } else {
                                            tipText = "设置[" + attr + "]:" + value;
                                        }
                                    }
                                }
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return tipText;
                            }
                            return "未找到时装([背包][锁住])";
                        }
                    }, "things": {
                        "add": function(text:String, value:Number):String
                        {
                            var thingsDef:* = Gaming.defineGroup.things.getDefineByCnName(text);
                            if (thingsDef && !thingsDef.isPartsB() && !thingsDef.isShopAutoUseB()) {
                                Gaming.PG.da.thingsBag.addDataByName(thingsDef.name, value);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加" + text + ":" + value;
                            }
                            return "未找到物品:" + text;
                        },
                        "addAllThings": function(text:String, value:Number):String
                        {
                            var thingsDef:* = null;
                            var thingsDefObj:Object = Gaming.defineGroup.things.obj;
                            for each (thingsDef in thingsDefObj) {
                                if (!thingsDef.isPartsB() && !thingsDef.isShopAutoUseB()) {
                                    Gaming.PG.da.thingsBag.addDataByName(thingsDef.name, value);
                                }
                            }
                            Gaming.uiGroup.bagUI.fleshAllBox();
                            return "添加所有物品:" + value;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            var thingsData:* = null;
                            var thingsDataArr:Array = Gaming.PG.da.thingsBag.dataArr;
                            for each (thingsData in thingsDataArr) {
                                if (thingsData.getCnName() == text) {
                                    thingsData.getFatherData().removeData(thingsData);
                                    Gaming.uiGroup.bagUI.fleshAllBox();
                                    return "删除:" + thingsData.getCnName();
                                }
                            }
                            return "未找到物品:" + text;
                        },
                        "removeAll": function(text:String, value:Number):String
                        {
                            Gaming.PG.da.thingsBag.clearData();
                            Gaming.uiGroup.bagUI.fleshAllBox();
                            return "删除所有物品";
                        },
                        "nowNum": function(text:String, value:Number):String
                        {
                            var thingsSave:* = null;
                            var thingsSaveArr:Array = Gaming.PG.save.thingsBag.arr;
                            for each (thingsSave in thingsSaveArr) {
                                if (thingsSave.cnName == text) {
                                    thingsSave.nowNum = value;
                                    Gaming.uiGroup.bagUI.fleshAllBox();
                                    return "设置" + text + ":" + value;
                                }
                            }
                            return "未找到物品:" + text;
                        },
                        "allNowNum": function(text:String, value:Number):String
                        {
                            var thingsSave:* = null;
                            var thingsSaveArr:Array = Gaming.PG.save.thingsBag.arr;
                            for each (thingsSave in thingsSaveArr) {
                                thingsSave.nowNum = value;
                            }
                            Gaming.uiGroup.bagUI.fleshAllBox();
                            return "设置所有物品:" + value;
                        }
                    }, "gene": {
                        "add": function(text:String, value:Number):String
                        {
                            var nc:Array = text.split(",");
                            var geneCnName:String = nc[0];
                            var geneColor:String = toColor(nc[1]);
                            var geneDef:* = Gaming.defineGroup.gene.getDefineByCn(geneCnName);
                            if (geneDef) {
                                var geneData:* = Gaming.defineGroup.geneCreator.getTempSuperData(geneDef.name);
                                geneData.save.color = geneColor;
                                Gaming.PG.da.geneBag.addData(geneData);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加基因体:" + geneCnName;
                            }
                            return "未找到基因体:" + geneCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("name", text);
                        },
                        "color": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("color", toColor(text));
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("addLevel", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("lockB", Boolean(value));
                        },
                        "obj": function(text:String, value:Number):String
                        {
                            var pro:String = getPetProByCn(text);
                            if (pro) {
                                return this.changeGeneObj(pro, value, "obj");
                            }
                            return "未找到基因体属性:" + text;
                        },
                        "addTalentSkill": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("addSkill", getSkillByCn(text), "talentSkillArr");
                        },
                        "deleteTalentSkill": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("deleteSkill", getSkillByCn(text), "talentSkillArr");
                        },
                        "talentSkillArr": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("talentSkillArr", getOneTypeSkillArrByCnArr(text.split(","), "petSkill"));
                        },
                        "addLaterSkill": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("addSkill", getSkillByCn(text), "laterSkillArr");
                        },
                        "deleteLaterSkill": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("deleteSkill", getSkillByCn(text), "laterSkillArr");
                        },
                        "laterSkillArr": function(text:String, value:Number):String
                        {
                            return this.changeGeneObj("laterSkillArr", getOneTypeSkillArrByCnArr(text.split(","), "petSkill"));
                        },
                        "changeGeneObj": function(attr:String, value:* = null, type:String = ""):String
                        {
                            var isValid:Boolean = false;
                            var geneSave:* = null;
                            var geneData:* = null;
                            var geneDataArr:Array = Gaming.PG.da.geneBag.dataArr;
                            for each (geneData in geneDataArr) {
                                geneSave = geneData.save;
                                if (geneSave.lockB) {
                                    isValid = true;
                                    break;
                                }
                            }
                            if (isValid) {
                                var tipText:String = "";
                                if (attr == "addSkill") {
                                    geneSave[type].push(value);
                                    tipText = "添加基因体技能:" + value;
                                } else if (attr == "deleteSkill") {
                                    var geneSkillArr:Array = geneSave[type];
                                    var geneSkillIdx:int = geneSkillArr.indexOf(value);
                                    tipText = "未找到基因体技能:" + value;
                                    if (geneSkillIdx >= 0) {
                                        geneSkillArr.splice(geneSkillIdx, 1);
                                        geneSave[type] = geneSkillArr;
                                        tipText = "删除基因体技能:" + value;
                                    }
                                } else if (attr == "remove") {
                                    geneData.getFatherData().removeData(geneData);
                                    tipText = "删除:" + geneData.getCnName();
                                } else {
                                    if (type) {
                                        var geneProObj:Object = geneSave[type];
                                        geneProObj[attr] = value;
                                        geneSave[type] = geneProObj;
                                        tipText = "设置[" + type + "][" + attr + "]:" + value;
                                    } else {
                                        geneSave[attr] = value;
                                        if (typeof value == "object") {
                                            tipText = "设置[" + attr + "]:" + value.length + "个";
                                        } else {
                                            tipText = "设置[" + attr + "]:" + value;
                                        }
                                    }
                                }
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return tipText;
                            }
                            return "未找到基因体([背包][锁住])";
                        }
                    }, "parts": {
                        "add": function(text:String, value:Number):String
                        {
                            var partsDef:* = null;
                            var partsDefArr:Array = getAllPartsDefArr();
                            for each (partsDef in partsDefArr) {
                                if (partsDef.cnName == text) {
                                    Gaming.PG.da.partsBag.addDataByName(partsDef.name, value);
                                    Gaming.uiGroup.bagUI.fleshAllBox();
                                    return "添加" + text + ":" + value;
                                }
                            }
                            return "未找到零件:" + text;
                        },
                        "addAllParts": function(text:String, value:Number):String
                        {
                            var partsDef:* = null;
                            var partsDefArr:Array = getAllPartsDefArr();
                            for each (partsDef in partsDefArr) {
                                Gaming.PG.da.partsBag.addDataByName(partsDef.name, value);
                            }
                            Gaming.uiGroup.bagUI.fleshAllBox();
                            return "添加所有零件:" + value;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            var partsData:* = null;
                            var partsDataArr:Array = Gaming.PG.da.partsBag.dataArr;
                            for each (partsData in partsDataArr) {
                                if (partsData.getCnName() == text) {
                                    partsData.getFatherData().removeData(partsData);
                                    Gaming.uiGroup.bagUI.fleshAllBox();
                                    return "删除:" + partsData.getCnName();
                                }
                            }
                            return "未找到零件:" + text;
                        },
                        "removeAll": function(text:String, value:Number):String
                        {
                            Gaming.PG.da.partsBag.clearData();
                            Gaming.uiGroup.bagUI.fleshAllBox();
                            return "删除所有零件";
                        },
                        "nowNum": function(text:String, value:Number):String
                        {
                            var partsSave:* = null;
                            var partsSaveArr:Array = Gaming.PG.save.partsBag.arr;
                            for each (partsSave in partsSaveArr) {
                                if (partsSave.cnName == text) {
                                    partsSave.nowNum = value;
                                    Gaming.uiGroup.bagUI.fleshAllBox();
                                    return "设置" + text + ":" + value;
                                }
                            }
                            return "未找到零件:" + text;
                        },
                        "allNowNum": function(text:String, value:Number):String
                        {
                            var partsSave:* = null;
                            var partsSaveArr:Array = Gaming.PG.save.partsBag.arr;
                            for each (partsSave in partsSaveArr) {
                                partsSave.nowNum = value;
                            }
                            Gaming.uiGroup.bagUI.fleshAllBox();
                            return "设置所有零件:" + value;
                        }
                    }, "vehicle": {
                        "add": function(text:String, value:Number):String
                        {
                            var vehicleDef:* = Gaming.defineGroup.vehicle.getDefineByCn(text);
                            if (vehicleDef) {
                                var vehicleData:* = VehicleDataCreator.getTempData(vehicleDef, Gaming.PG.da);
                                Gaming.PG.da.equipBag.addData(vehicleData);
                                fleshUIBox("vehicleUI", "upgrade");
                                Gaming.uiGroup.vehicleUI.fleshBag();
                                return "添加载具:" + text;
                            }
                            return "未找到载具:" + text;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("imgName", text);
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("addLevel", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("evo");
                        },
                        "mainMulAddLv": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("mainMulAddLv", value);
                        },
                        "subMulAddLv": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("subMulAddLv", value);
                        },
                        "attackMulAddLv": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("attackMulAddLv", value);
                        },
                        "lifeMulAddLv": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("lifeMulAddLv", value);
                        },
                        "upLv": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("upLv", value);
                        },
                        "study": function(text:String, value:Number):String
                        {
                            return this.changeVehicleSkillObj(text);
                        },
                        "skillLv": function(text:String, value:Number):String
                        {
                            return this.changeVehicleSkillObj(text, value);
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeVehicleObj("getTime", text) + "\n";
                            tipText += this.changeVehicleObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeVehicleObj("inHouseTime", text);
                        },
                        "changeVehicleObj": function(attr:String, value:* = null):String
                        {
                            var vehicleData:* = Gaming.uiGroup.vehicleUI.nowData;
                            if (vehicleData) {
                                var tipText:String = "";
                                var vehicleSave:* = vehicleData.save;
                                if (attr == "evo") {
                                    var vehicleEvoData:* = vehicleData.getEvolutionData();
                                    if (vehicleEvoData) {
                                        vehicleData.changeToOneData(vehicleEvoData);
                                        tipText = "进阶载具";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "remove") {
                                    vehicleData.getFatherData().removeData(vehicleData);
                                    tipText = "删除:" + vehicleData.getCnName();
                                } else {
                                    vehicleSave[attr] = value;
                                    if (typeof value == "object") {
                                        tipText = "设置[" + attr + "]:" + value.length + "个";
                                    } else {
                                        tipText = "设置[" + attr + "]:" + value;
                                    }
                                }
                                fleshUIBox("vehicleUI", "upgrade");
                                Gaming.uiGroup.vehicleUI.fleshBag();
                                return tipText;
                            }
                            return "未找到载具([载具][升级])";
                        },
                        "changeVehicleSkillObj": function(skill:String, value:* = null):String
                        {
                            var vehicleData:* = Gaming.uiGroup.vehicleUI.nowData;
                            if (vehicleData) {
                                var tipText:String = "未找到载具技能:" + skill;
                                var vehicleSave:* = vehicleData.save;
                                var vehicleSkillDef:* = getVehicleStudySkillDefByCn(vehicleData, skill);
                                if (vehicleSkillDef) {
                                    if (value) {
                                        var vehicleSkill:* = null;
                                        var vehicleSkillArr:Array = vehicleSave.skill.arr;
                                        for each (vehicleSkill in vehicleSkillArr) {
                                            if (vehicleSkill.baseLabel == vehicleSkillDef.baseLabel) {
                                                var vehicleSkillMaxLv:int = vehicleSkill.getOriginalDefine().getMaxLevel();
                                                value = clamp(value, 1, vehicleSkillMaxLv);
                                                vehicleSkill.lv = value;
                                                tipText = "设置" + skill + ":" + value;
                                            }
                                        }
                                    } else {
                                        vehicleData.skill.addSkillByLabel(vehicleSkillDef.baseLabel, vehicleSkillDef.mustLv);
                                        tipText = "学习指定载具技能:" + skill;
                                    }
                                }
                                fleshUIBox("vehicleUI", "upgrade");
                                Gaming.uiGroup.vehicleUI.fleshBag();
                                return tipText;
                            }
                            return "未找到载具([载具][升级])";
                        }
                    }, "jewelry": {
                        "add": function(text:String, value:Number):String
                        {
                            var nl:Array = text.split(",");
                            var jewelryCnName:String = nl[0];
                            var jewelryLevel:int = int(nl[1]);
                            var jewelryDef:* = Gaming.defineGroup.jewelry.getJewelryDefineByCn(jewelryCnName);
                            if (jewelryDef) {
                                var jewelryLv:int = clamp(jewelryLevel, 1, jewelryDef.maxLv);
                                var jewelryName:String = jewelryDef.baseLabel + "_" + jewelryLv;
                                var jewelryDefine:* = Gaming.defineGroup.jewelry.getDefine(jewelryName);
                                var jewelrySave:* = JewelryDataCreator.getSaveByDefine(jewelryDefine, value);
                                Gaming.PG.da.equipBag.addSave(jewelrySave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加" + jewelryDefine.getTrueCnName() + ":" + value;
                            }
                            return "未找到饰品:" + jewelryCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("imgName", text);
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("strengthenLv", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("evo");
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeJewelryObj("getTime", text) + "\n";
                            tipText += this.changeJewelryObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeJewelryObj("inHouseTime", text);
                        },
                        "changeJewelryObj": function(attr:String, value:* = null):String
                        {
                            var jewelryData:* = Gaming.uiGroup.forgingUI.jewelryUpgradeBoard.nowData;
                            if (jewelryData) {
                                var tipText:String = "";
                                var jewelrySave:* = jewelryData.save;
                                if (attr == "evo") {
                                    var nextJewelrySkillDef:* = jewelryData.jewelryDefine.getNextSkillDefine();
                                    if (nextJewelrySkillDef) {
                                        var jewelryUpradeData:* = jewelryData.getUpradeData();
                                        jewelryUpradeData.save.nowNum = jewelrySave.nowNum;
                                        jewelryData.changeToOneData(jewelryUpradeData);
                                        tipText = "进阶饰品";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "remove") {
                                    jewelryData.getFatherData().removeData(jewelryData);
                                    tipText = "删除:" + jewelryData.getCnName();
                                } else {
                                    jewelrySave[attr] = value;
                                    if (typeof value == "object") {
                                        tipText = "设置[" + attr + "]:" + value.length + "个";
                                    } else {
                                        tipText = "设置[" + attr + "]:" + value;
                                    }
                                }
                                fleshUIBox("forgingUI", "jewelryUpgrade");
                                return tipText;
                            }
                            return "未找到饰品([锻造][其他进阶][饰品])";
                        }
                    }, "shield": {
                        "add": function(text:String, value:Number):String
                        {
                            var nl:Array = text.split(",");
                            var shieldCnName:String = nl[0];
                            var shieldLevel:int = int(nl[1]);
                            var shieldDef:* = Gaming.defineGroup.shield.getShieldDefineByCn(shieldCnName);
                            if (shieldDef) {
                                var shieldLv:int = clamp(shieldLevel, 1, shieldDef.maxLv);
                                var shieldName:String = shieldDef.baseLabel + "_" + shieldLv;
                                var shieldDefine:* = Gaming.defineGroup.shield.getDefine(shieldName);
                                var shieldSave:* = ShieldDataCreator.getSaveByDefine(shieldDefine, value);
                                Gaming.PG.da.equipBag.addSave(shieldSave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加" + shieldDefine.getTrueCnName() + ":" + value;
                            }
                            return "未找到护盾:" + shieldCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("imgName", text);
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("strengthenLv", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("evo");
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeShieldObj("getTime", text) + "\n";
                            tipText += this.changeShieldObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeShieldObj("inHouseTime", text);
                        },
                        "changeShieldObj": function(attr:String, value:* = null):String
                        {
                            var shieldData:* = Gaming.uiGroup.forgingUI.shieldUpgradeBoard.nowData;
                            if (shieldData) {
                                var tipText:String = "";
                                var shieldSave:* = shieldData.save;
                                if (attr == "evo") {
                                    var nextShieldSkillDef:* = shieldData.shieldDefine.getNextSkillDefine();
                                    if (nextShieldSkillDef) {
                                        var shieldUpradeData:* = shieldData.getUpradeData();
                                        shieldUpradeData.save.nowNum = shieldSave.nowNum;
                                        shieldData.changeToOneData(shieldUpradeData);
                                        tipText = "进阶护盾";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "remove") {
                                    shieldData.getFatherData().removeData(shieldData);
                                    tipText = "删除:" + shieldData.getCnName();
                                } else {
                                    shieldSave[attr] = value;
                                    if (typeof value == "object") {
                                        tipText = "设置[" + attr + "]:" + value.length + "个";
                                    } else {
                                        tipText = "设置[" + attr + "]:" + value;
                                    }
                                }
                                fleshUIBox("forgingUI", "shieldUpgrade");
                                return tipText;
                            }
                            return "未找到护盾([锻造][其他进阶][护盾])";
                        }
                    }, "weapon": {
                        "add": function(text:String, value:Number):String
                        {
                            var nl:Array = text.split(",");
                            var weaponCnName:String = nl[0];
                            var weaponLevel:int = int(nl[1]);
                            var weaponDef:* = Gaming.defineGroup.weapon.getWeaponDefineByCn(weaponCnName);
                            if (weaponDef) {
                                var weaponLv:int = clamp(weaponLevel, 1, weaponDef.getMaxLv());
                                var weaponName:String = weaponDef.baseLabel + "_" + weaponLv;
                                var weaponDefine:* = Gaming.defineGroup.weapon.getDefine(weaponName);
                                var weaponSave:* = WeaponDataCreator.getSaveByDefine(weaponDefine, value);
                                Gaming.PG.da.equipBag.addSave(weaponSave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加" + weaponDefine.getTrueCnName() + ":" + value;
                            }
                            return "未找到副手:" + weaponCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("imgName", text);
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("strengthenLv", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("evo");
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeWeaponObj("getTime", text) + "\n";
                            tipText += this.changeWeaponObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeWeaponObj("inHouseTime", text);
                        },
                        "changeWeaponObj": function(attr:String, value:* = null):String
                        {
                            var weaponData:* = Gaming.uiGroup.forgingUI.weaponUpgradeBoard.nowData;
                            if (weaponData) {
                                var tipText:String = "";
                                var weaponSave:* = weaponData.save;
                                if (attr == "evo") {
                                    var weaponUpradeData:* = weaponData.getUpradeData();
                                    if (weaponUpradeData) {
                                        weaponUpradeData.save.nowNum = weaponSave.nowNum;
                                        weaponData.changeToOneData(weaponUpradeData);
                                        tipText = "进阶副手";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "remove") {
                                    weaponData.getFatherData().removeData(weaponData);
                                    tipText = "删除:" + weaponData.getCnName();
                                } else {
                                    weaponSave[attr] = value;
                                    if (typeof value == "object") {
                                        tipText = "设置[" + attr + "]:" + value.length + "个";
                                    } else {
                                        tipText = "设置[" + attr + "]:" + value;
                                    }
                                }
                                fleshUIBox("forgingUI", "weaponUpgrade");
                                return tipText;
                            }
                            return "未找到副手([锻造][其他进阶][副手])";
                        }
                    }, "device": {
                        "add": function(text:String, value:Number):String
                        {
                            var nl:Array = text.split(",");
                            var deviceCnName:String = nl[0];
                            var deviceLevel:int = int(nl[1]);
                            var deviceDef:* = Gaming.defineGroup.device.getDeviceDefineByCn(deviceCnName);
                            if (deviceDef) {
                                var deviceLv:int = clamp(deviceLevel, 1, deviceDef.getMaxLevel());
                                var deviceName:String = deviceDef.baseLabel + "_" + deviceLv;
                                var deviceDefine:* = Gaming.defineGroup.device.getDefine(deviceName);
                                var deviceSave:* = DeviceDataCreator.getSaveByDefine(deviceDefine, value);
                                Gaming.PG.da.equipBag.addSave(deviceSave);
                                Gaming.uiGroup.bagUI.fleshAllBox();
                                return "添加" + deviceDefine.getTrueCnName() + ":" + value;
                            }
                            return "未找到装置:" + deviceCnName;
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("remove");
                        },
                        "name": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("name", text);
                        },
                        "imgName": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("imgName", text);
                        },
                        "itemsLevel": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("itemsLevel", value);
                        },
                        "addLevel": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("addLevel", value);
                        },
                        "strengthenLv": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("strengthenLv", value);
                        },
                        "lockB": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("lockB", Boolean(value));
                        },
                        "newB": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("newB", Boolean(value));
                        },
                        "evo": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("evo");
                        },
                        "getTime": function(text:String, value:Number):String
                        {
                            var tipText:String = this.changeDeviceObj("getTime", text) + "\n";
                            tipText += this.changeDeviceObj("severTime", text);
                            return tipText;
                        },
                        "inHouseTime": function(text:String, value:Number):String
                        {
                            return this.changeDeviceObj("inHouseTime", text);
                        },
                        "changeDeviceObj": function(attr:String, value:* = null):String
                        {
                            var deviceData:* = Gaming.uiGroup.forgingUI.deviceUpgradeBoard.nowData;
                            if (deviceData) {
                                var tipText:String = "";
                                var deviceSave:* = deviceData.save;
                                if (attr == "evo") {
                                    var nextDeviceSkillDef:* = deviceData.deviceDefine.getNextSkillDefine();
                                    if (nextDeviceSkillDef) {
                                        var deviceUpradeData:* = deviceData.getUpradeData();
                                        deviceUpradeData.save.nowNum = deviceSave.nowNum;
                                        deviceData.changeToOneData(deviceUpradeData);
                                        tipText = "进阶装置";
                                    } else {
                                        tipText = "已进阶至最高等级";
                                    }
                                } else if (attr == "remove") {
                                    deviceData.getFatherData().removeData(deviceData);
                                    tipText = "删除:" + deviceData.getCnName();
                                } else {
                                    deviceSave[attr] = value;
                                    if (typeof value == "object") {
                                        tipText = "设置[" + attr + "]:" + value.length + "个";
                                    } else {
                                        tipText = "设置[" + attr + "]:" + value;
                                    }
                                }
                                fleshUIBox("forgingUI", "deviceUpgrade");
                                return tipText;
                            }
                            return "未找到装置([锻造][其他进阶][装置])";
                        }
                    }, "peak": {
                        "lv": function(text:String, value:Number):String
                        {
                            return this.changePeakObj("lv", value);
                        },
                        "exp": function(text:String, value:Number):String
                        {
                            return this.changePeakObj("exp", value);
                        },
                        "dayExp": function(text:String, value:Number):String
                        {
                            return this.changePeakObj("dayExp", value);
                        },
                        "dpN": function(text:String, value:Number):String
                        {
                            return this.changePeakObj("dpN", value);
                        },
                        "dpDay": function(text:String, value:Number):String
                        {
                            return this.changePeakObj("dpDay", value);
                        },
                        "pointObj": function(text:String, value:Number):String
                        {
                            var pp:Array = text.split(",");
                            var page:int = clamp(pp[0], 1, 3);
                            var proText:String = pp[1];
                            var pro:String = getPeakProByCn(proText);
                            if (pro) {
                                return this.changePeakObj(pro, value, page, true);
                            }
                            return "未找到巅峰属性:" + proText;
                        },
                        "changePeakObj": function(attr:String, value:Number, page:int = 0, isPoint:Boolean = false):String
                        {
                            var tipText:String = "";
                            var peakSave:* = Gaming.PG.save.peak;
                            if (isPoint) {
                                var type:String = "pointObj";
                                if (page > 1) {
                                    type += page;
                                }
                                peakSave[type].setAttribute(attr, value);
                                tipText = "设置[" + type + "][" + attr + "]:" + value;
                            } else {
                                peakSave[attr] = value;
                                tipText = "设置[" + attr + "]:" + value;
                            }
                            UIShow.hideNowApp();
                            Gaming.uiGroup.peakUI.show();
                            return tipText;
                        }
                    }, "head": {
                        "add": function(text:String, value:Number):String
                        {
                            var headDef:* = Gaming.defineGroup.head.getDefineByCn(text);
                            if (headDef) {
                                var nowTime:String = Gaming.api.save.getNowServerDate().getStr();
                                Gaming.PG.da.head.addHead(headDef.name, nowTime);
                                fleshUIBox("headUI", "have");
                                return "添加称号:" + text;
                            }
                            return "未找到称号:" + text;
                        },
                        "addAllHead": function(text:String, value:Number):String
                        {
                            var headDef:* = null;
                            var headDefArr:Array = Gaming.defineGroup.head.arr;
                            var nowTime:String = Gaming.api.save.getNowServerDate().getStr();
                            for each (headDef in headDefArr) {
                                Gaming.PG.da.head.addHead(headDef.name, nowTime);
                            }
                            fleshUIBox("headUI", "have");
                            return "添加所有称号";
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            var headDef:* = Gaming.defineGroup.head.getDefineByCn(text);
                            if (headDef) {
                                var headName:String = "";
                                var headSaveObj:Object = Gaming.PG.save.head.obj;
                                for (headName in headSaveObj) {
                                    if (headName == headDef.name) {
                                        delete headSaveObj[headName];
                                        fleshUIBox("headUI", "have");
                                        return "删除:" + text;
                                    }
                                }
                            }
                            return "未找到称号:" + text;
                        },
                        "removeAll": function(text:String, value:Number):String
                        {
                            var headSave:* = Gaming.PG.save.head;
                            headSave.nowHead = "";
                            headSave.obj = {};
                            headSave.nowIndex = 0;
                            fleshUIBox("headUI", "have");
                            return "删除所有称号";
                        }
                    }, "achieve": {
                        "complete": function(text:String, value:Number):String
                        {
                            var achieveName:String = this.getName_achieve(text);
                            if (achieveName) {
                                var achieveData:* = Gaming.PG.da.achieve.getDataByName(achieveName);
                                if (!achieveData.isCompleteB()) {
                                    achieveData.complete();
                                    this.fleshAchieveUI(true, achieveName);
                                    return "解锁勋章:" + text;
                                }
                                return "已解锁";
                            }
                            return "未找到勋章:" + text;
                        },
                        "completeAllAchieve": function(text:String, value:Number):String
                        {
                            Gaming.PG.da.achieve.completeAll();
                            this.fleshAchieveUI(false);
                            return "解锁所有勋章";
                        },
                        "remove": function(text:String, value:Number):String
                        {
                            var achieveName:String = this.getName_achieve(text);
                            if (achieveName) {
                                var achieveData:* = Gaming.PG.da.achieve.getDataByName(achieveName);
                                if (achieveData.isCompleteB()) {
                                    achieveData.clear();
                                    achieveData.newB = false;
                                    this.fleshAchieveUI(true, achieveName);
                                    return "删除:" + text;
                                }
                            }
                            return "未找到勋章:" + text;
                        },
                        "removeAll": function(text:String, value:Number):String
                        {
                            var achieveDef:* = null;
                            var achieveDefObj:Object = Gaming.defineGroup.achieve.obj;
                            for each (achieveDef in achieveDefObj) {
                                var achieveData:* = Gaming.PG.da.achieve.getDataByName(achieveDef.name);
                                if (achieveData.isCompleteB()) {
                                    achieveData.clear();
                                    achieveData.newB = false;
                                }
                            }
                            this.fleshAchieveUI(true);
                            return "删除所有勋章";
                        },
                        "getName_achieve": function(cnName:String):* {
                            var achieveDef:* = null;
                            var achieveDefObj:Object = Gaming.defineGroup.achieve.obj;
                            for each (achieveDef in achieveDefObj) {
                                if (achieveDef.cnName == cnName) {
                                    return achieveDef.name;
                                }
                            }
                            return "";
                        },
                        "fleshAchieveUI": function(fleshGroup:Boolean, gotoName:String = ""):void
                        {
                            if (fleshGroup) {
                                Gaming.PG.da.achieve.fleshAffterComplete();
                            }
                            if (gotoName == "") {
                                gotoName = "demonTime_1";
                            }
                            UIShow.hideNowApp();
                            Gaming.uiGroup.achieveUI.gotoName(gotoName);
                        }
                    }, "union": {
                        "lv": function(text:String, value:Number):String
                        {
                            return this.changeUnionBuildingObj(text, "lv", value);
                        },
                        "copyCurUnionMemberData": function(text:String, value:Number):String
                        {
                            var unionMemberList:* = Gaming.PG.da.union.nowMemberList;
                            copy(getUnionMemberInfoToText(unionMemberList.arr));
                            return "复制当前军队成员数据";
                        },
                        "copyOneUnionMemberData": function(text:String, value:Number):String
                        {
                            var saveIdx:int = Gaming.getSaveIndex();
                            var unionId:int = int(value);
                            Gaming.api.union.member.getUnionMembers(saveIdx, unionId, this.getRankListByUnionId, this.getRankListError);
                            return "复制指定军队成员数据,军队ID:" + unionId;
                        },
                        "getRankListByUnionId": function(json:String):void
                        {
                            var unionMemberList:* = new MemberListInfo();
                            unionMemberList.inData_byJson(json, -1);
                            unionMemberList.sort();
                            copy(getUnionMemberInfoToText(unionMemberList.arr));
                        },
                        "getRankListError": function(errorText:String):void
                        {
                            Gaming.uiGroup.alertBox.showError(errorText);
                        },
                        "changeUnionBuildingObj": function(building:String, attr:String, value:Number):String
                        {
                            var buildingDef:* = null;
                            var buildingDefArr:Array = Gaming.defineGroup.union.building.arr;
                            for each (buildingDef in buildingDefArr) {
                                if (buildingDef.cnName == building) {
                                    var buildingDataGroup:* = Gaming.PG.da.union.building;
                                    var buildingData:* = buildingDataGroup.getData(buildingDef.name);
                                    if (buildingData) {
                                        value = clamp(value, 1, buildingData.getNowMaxLv());
                                        buildingData.save[attr] = value;
                                        if (buildingDef.fleshAddDataB) {
                                            buildingDataGroup.playerData.fleshAllByEquip();
                                        }
                                        if (buildingData == buildingDataGroup.geology.buildData) {
                                            buildingDataGroup.geology.fleshDefineByLv();
                                        }
                                        Gaming.uiGroup.unionUI.buildingBoard.fleshData();
                                        return "设置[" + building + "][" + attr + "]:" + value;
                                    }
                                }
                            }
                            return "未找到建筑:" + building;
                        }
                    }, "city": {
                        "allNum": function(text:String, value:Number):String
                        {
                            return this.changeCityObj("allNum", value);
                        },
                        "changeCityObj": function(attr:String, value:Number):String
                        {
                            Gaming.PG.save.city[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        }
                    }, "vip": {
                        "pay": function(text:String, value:Number):String
                        {
                            Gaming.api.shop.payMoney(value);
                            PayCtrl.getBalance();
                            return "模拟充值:" + value;
                        },
                        "level": function(text:String, value:Number):String
                        {
                            var vipLv:int = clamp(value, 1, 10);
                            return this.changeVIPObj("level", vipLv);
                        },
                        "obj": function(text:String, value:Number):String
                        {
                            return this.changeVIPRecordObj("obj", text, value);
                        },
                        "dayObj": function(text:String, value:Number):String
                        {
                            return this.changeVIPRecordObj("dayObj", text, value);
                        },
                        "upLevelObj": function(text:String, value:Number):String
                        {
                            return this.changeVIPRecordObj("upLevelObj", text, value);
                        },
                        "nO": function(text:String, value:Number):String
                        {
                            return this.changeVIPRecordObj("nO", text, value);
                        },
                        "vipZuobiPan": function(text:String, value:Number):String
                        {
                            this.changeVIPObj("level", 0);
                            this.changeVIPObj("obj", {});
                            this.changeVIPObj("dayObj", {});
                            this.changeVIPObj("upLevelObj", {});
                            this.changeVIPObj("nO", {});
                            Gaming.api.shop.completed = false;
                            PayCtrl.getBalance();
                            return "解除VIP作弊记录完成";
                        },
                        "changeVIPObj": function(attr:String, value:*):String
                        {
                            Gaming.PG.save.vip[attr] = value;
                            return "设置[" + attr + "]:" + value;
                        },
                        "changeVIPRecordObj": function(type:String, attr:String, value:Number):String
                        {
                            var vipLv:int = clamp(attr, 1, 10);
                            var vipDef:* = Gaming.defineGroup.vip.getDefineByIndex(vipLv);
                            if (vipDef) {
                                var vipId:String = vipDef.getId();
                                if (vipId) {
                                    var statusValue:Boolean = Boolean(value);
                                    Gaming.PG.save.vip[type][vipId] = statusValue;
                                    return "设置[" + type + "][" + vipId + "]:" + statusValue;
                                }
                            }
                            return "未找到VIP等级:" + vipLv;
                        }
                    }, "tower": {
                        "winOne": function(text:String, value:Number):String
                        {
                            return this.changeTowerWinObj(Number(text), value);
                        },
                        "winAll": function(text:String, value:Number):String
                        {
                            return this.changeTowerWinObj(-1, value, true);
                        },
                        "getGiftAll": function(text:String, value:Number):String
                        {
                            var n:Number = 0;
                            var towerDef:* = null;
                            var towerDefArr:Array = Gaming.defineGroup.tower.getUIArr();
                            var towerWinSave:* = Gaming.PG.save.tower.dO;
                            var towerGiftSave:* = Gaming.PG.save.tower.gO;
                            for each (towerDef in towerDefArr) {
                                var layer:String = String(towerDef.lv);
                                if (towerWinSave.haveAttribute(layer)) {
                                    var winDiff:int = int(towerWinSave.getAttribute(layer));
                                    if (towerGiftSave.haveAttribute(layer)) {
                                        var giftDiff:int = int(towerGiftSave.getAttribute(layer));
                                        if (giftDiff >= winDiff) {
                                            continue;
                                        }
                                    }
                                    var towerGift:* = Gaming.PG.da.tower.getCanGift(towerDef);
                                    if (towerGift) {
                                        GiftAddit.add(towerGift);
                                        n++;
                                    }
                                    towerGiftSave.setAttribute(layer, winDiff);
                                }
                            }
                            return "领取已通关幻塔奖励:" + n + "次";
                        },
                        "unendLv": function(text:String, value:Number):String
                        {
                            return this.changeTowerObj("unendLv", value);
                        },
                        "pointObj": function(text:String, value:Number):String
                        {
                            var pp:Array = text.split(",");
                            var page:int = clamp(pp[0], 1, 3) - 1;
                            var proText:String = pp[1];
                            var pro:String = getUnendProByCn(proText);
                            if (pro) {
                                return this.changeTowerObj(pro, value, page, true);
                            }
                            return "未找到虚天塔属性:" + proText;
                        },
                        "changeTowerObj": function(attr:String, value:Number, page:int = 0, isPoint:Boolean = false):String
                        {
                            var tipText:String = "";
                            var towerSave:* = Gaming.PG.save.tower;
                            if (isPoint) {
                                var type:String = "p" + page;
                                towerSave[type].setAttribute(attr, value);
                                tipText = "设置[" + type + "][" + attr + "]:" + value;
                            } else {
                                towerSave[attr] = value;
                                tipText = "设置[" + attr + "]:" + value;
                            }
                            return tipText;
                        },
                        "changeTowerWinObj": function(layer:Number, diff:Number, isLayerAll:Boolean = false):String
                        {
                            var tipText:String = "";
                            var towerDef:* = null;
                            var towerDefArr:Array = Gaming.defineGroup.tower.getUIArr();
                            var towerWinSave:* = Gaming.PG.save.tower.dO;
                            var diffValue:int = clamp(diff, 1, 4);
                            if (isLayerAll) {
                                for each (towerDef in towerDefArr) {
                                    towerWinSave.setAttribute(towerDef.lv, diffValue);
                                }
                                tipText = "通关所有幻塔层数,难度:" + diffValue;
                            } else {
                                tipText = "未找到指定幻塔层数:" + layer;
                                for each (towerDef in towerDefArr) {
                                    if (towerDef.lv == layer) {
                                        towerWinSave.setAttribute(layer, diffValue);
                                        tipText = "通关幻塔第" + layer + "层,难度:" + diffValue;
                                        break;
                                    }
                                }
                            }
                            return tipText;
                        }
                    }, "define": {
                        "equip": function(text:String, value:Number):String
                        {
                            return this.copyCode("equip");
                        },
                        "things": function(text:String, value:Number):String
                        {
                            return this.copyCode("things");
                        },
                        "skill": function(text:String, value:Number):String
                        {
                            return this.copyCode("skill");
                        },
                        "copyCode": function(type:String):String
                        {
                            var codeData = "";
                            var dataDef:* = null;
                            var dataDefObj:Object = Gaming.defineGroup[type].obj;
                            for each (dataDef in dataDefObj) {
                                var defInfo:String = dataDef.cnName + "---" + dataDef.name + "\n";
                                codeData += defInfo;
                            }
                            copy(codeData);
                            return "查询定义:" + type;
                        }
                    }};
            Gaming.uiGroup.alertBox.showSuccess(extendMethods[type][method](string, number));
            break;
    }
}
