package UI.union.member
{
   import UI.*;
   import UI.base.NormalUI;
   import UI.base.button.*;
   import UI.base.event.*;
   import UI.top.*;
   import com.sounto.oldUtils.*;
   import dataAll._app.union.*;
   import dataAll._app.union.define.*;
   import dataAll._app.union.info.*;
   import flash.display.*;
   import flash.events.*;
   import flash.system.*;
   import w_test.bug.*;
   
   public class UnionMemberBoard extends NormalUI
   {
       
      
      private var shape:Shape;
      
      private var barTag:Sprite;
      
      private var pageTag:Sprite;
      
      private var checkBtnSp:MovieClip;
      
      private var conditionBtnSp:MovieClip;
      
      private var battleBtnSp:MovieClip;
      
      private var checkBtn:NormalBtn;
      
      private var conditionBtn:NormalBtn;
      
      private var battleBtn:NormalBtn;
      
      private var maxBarNum:int = 10;
      
      private var nowPage:int = 0;
      
      private var topBox:TopBarBox;
      
      private var btnArr:Array;
      
      private var checkBoard:UnionCheckBoard;
      
      private var conditionBoard:UnionConditionBoard;
      
      private var removeMemberInfo:MemberInfo = null;
      
      private var roleMemberInfo:MemberInfo = null;
      
      public function UnionMemberBoard()
      {
         this.shape = new Shape();
         this.checkBtn = new NormalBtn();
         this.conditionBtn = new NormalBtn();
         this.battleBtn = new NormalBtn();
         this.topBox = new TopBarBox();
         this.btnArr = [];
         this.checkBoard = new UnionCheckBoard();
         this.conditionBoard = new UnionConditionBoard();
         super();
      }
      
      override public function setImg(img0:Sprite) : void
      {
         var list0:MemberBarBtnList = null;
         elementNameArr = ["barTag","pageTag","checkBtnSp","conditionBtnSp","battleBtnSp"];
         super.setImg(img0);
         this.initBar();
         addChild(this.checkBtn);
         this.checkBtn.setImg(this.checkBtnSp);
         this.checkBtn.activedAndEnabled = false;
         this.checkBtn.setName("审核成员");
         this.checkBtn.addEventListener(MouseEvent.CLICK,this.checkBtnClick);
         addChild(this.conditionBtn);
         this.conditionBtn.setImg(this.conditionBtnSp);
         this.conditionBtn.activedAndEnabled = false;
         this.conditionBtn.setName("设置收人条件");
         this.conditionBtn.addEventListener(MouseEvent.CLICK,this.conditionBtnClick);
         addChild(this.battleBtn);
         this.battleBtn.setImg(this.battleBtnSp);
         this.battleBtn.setName("复制成员数据");
         this.battleBtn.addEventListener(MouseEvent.CLICK,this.battleBtnClick);
         for(var i:int = 0; i < this.maxBarNum; i++)
         {
            list0 = new MemberBarBtnList();
            list0.setImg(Gaming.swfLoaderManager.getResource("UnionUI","memberBarBtnList"));
            list0.index = i;
            list0.clickFun = this.barBtnClick;
            this.btnArr.push(list0);
            addChild(list0);
            list0.visible = false;
         }
         addChild(this.checkBoard);
         this.checkBoard.setImg(Gaming.swfLoaderManager.getResource("UnionUI","checkBoard"));
         this.checkBoard.visible = false;
         addChild(this.conditionBoard);
         this.conditionBoard.setImg(Gaming.swfLoaderManager.getResource("UnionUI","conditionBoard"));
         this.conditionBoard.visible = false;
      }
      
      private function initBar() : void
      {
         this.topBox.initTitle("UnionUI/memberBar",0,true);
         this.topBox.arg.init(1,this.maxBarNum,0,0);
         this.topBox.evt.setWant(true,true);
         this.barTag.addChild(this.topBox);
         this.topBox.pageBox.setToNormalBtn();
         this.topBox.pageBox.setXY_bySp(this.pageTag,this.barTag);
         this.topBox.pageBox.addEventListener(ClickEvent.ON_SHOW_PAGE,this.showPageEvent);
         this.topBox.addEventListener(ClickEvent.ON_CLICK,this.barClick);
         this.topBox.addEventListener(ClickEvent.ON_OVER,this.barOver);
         this.topBox.addEventListener(ClickEvent.ON_OUT,this.barOut);
         this.topBox.otherFleshFun = this.fleshBtnListByBar;
      }
      
      override public function show() : void
      {
         super.show();
         this.fleshData();
         this.getRankList();
      }
      
      override protected function SET(str0:String, value0:Object) : void
      {
         if(!this[str0])
         {
            this[str0] = value0;
         }
      }
      
      private function fleshData() : void
      {
         this.checkBtn.visible = Gaming.PG.da.union.haveCheckRightB();
         this.conditionBtn.visible = this.checkBtn.visible;
      }
      
      private function get unionData() : UnionData
      {
         return Gaming.PG.da.union;
      }
      
      private function getRankList() : void
      {
         Gaming.uiGroup.unionUI.flesher.fleshMemberList(this.yes_getRankList);
      }
      
      private function yes_getRankList(u0:MemberListInfo) : void
      {
         this.topBox.inData(u0);
         this.fleshBtnListByBar();
         if(this.unionData.canUploadUnionB())
         {
            if(TestCode.code == TestCode.unionUpload)
            {
               Gaming.uiGroup.unionUI.flesher.fleshUnionInfo();
            }
         }
      }
      
      private function fleshBtnListByBar() : void
      {
         var n:* = undefined;
         var list0:MemberBarBtnList = null;
         var bar0:TopBar = null;
         var m0:MemberInfo = null;
         for(n in this.btnArr)
         {
            list0 = this.btnArr[n];
            bar0 = this.topBox.gripArr[this.topBox.pageBox.getNowPage() * this.maxBarNum + n];
            if(Boolean(bar0))
            {
               m0 = bar0.itemsData as MemberInfo;
               list0.visible = true;
               list0.itemsData = bar0.itemsData as MemberInfo;
               list0.setVisible(Gaming.PG.da.union);
               list0.x = bar0.x + this.barTag.x;
               list0.y = bar0.y + this.barTag.y;
            }
            else
            {
               list0.visible = false;
            }
         }
      }
      
      private function showPageEvent(num0:int) : void
      {
         this.fleshBtnListByBar();
      }
      
      private function barClick(e:ClickEvent) : void
      {
         if(Boolean(this.unionData.isKingB()) || Boolean(UnionData.ROLE_B))
         {
            this.roleMemberInfo = e.childData as MemberInfo;
            Gaming.uiGroup.alertBox.textInput.showTextInput("设置职位为","",this.afterBarClick);
         }
      }
      
      private function afterBarClick(s0:String) : void
      {
         var vnum0:int = 0;
         var m0:MemberInfo = null;
         var v0:int = 0;
         if(s0 == "副司令")
         {
            v0 = int(UnionRole.viceKingId);
            vnum0 = int(this.unionData.nowMemberList.getRoleNum(UnionRole.viceKingId));
            if(vnum0 >= 1)
            {
               UIOrder.alertError("一个军队只能设置1个副司令。");
               return;
            }
         }
         if(v0 > 0)
         {
            m0 = this.roleMemberInfo;
            Gaming.uiGroup.connectUI.show("设置 " + m0.extraObj.playerName + " 职位为：" + s0);
            Gaming.api.union.member.setRole(Gaming.getSaveIndex(),m0.uId,m0.index,v0,this.yes_roleMember,this.no_roleMember);
         }
      }
      
      private function barOver(e:ClickEvent) : void
      {
         var nowM0:MemberInfo = this.unionData.nowMember;
         var nowTime0:StringDate = Gaming.api.save.getNowServerDate();
         var m0:MemberInfo = e.childData as MemberInfo;
         var s0:String = "玩家名称：<yellow " + m0.extraObj.playerName + "/>\n";
         s0 += "等级：<yellow " + m0.extraObj.lv + "/>\n";
         s0 += "生命值：<yellow " + m0.extraObj.life + "/>\n";
         s0 += "VIP：<yellow " + m0.extraObj.vip + "/>\n";
         if(m0.extraObj.loginTime != "")
         {
            s0 += "最近登录时间：<orange " + m0.extraObj.loginTime + "/>\n";
         }
         if(Boolean(nowM0) && m0.samePan(nowM0))
         {
            s0 += nowM0.getMemberBattleTip();
         }
         else
         {
            s0 += m0.getMemberBattleTip();
         }
         s0 += "\n今日贡献：<green " + m0.extraObj.getDayCon(nowTime0) + "/>";
         s0 += UnionData.getContributionCountStrBy(nowTime0,m0.extraObj.conObj);
         Gaming.uiGroup.tipBox.textTip.showFollowText(s0);
      }
      
      private function barOut(e:ClickEvent) : void
      {
         Gaming.uiGroup.tipBox.hide();
      }
      
      private function barBtnClick(i0:MemberInfo, label0:String) : void
      {
         if(label0 == "expel")
         {
            this.removeMember(i0);
         }
         else if(label0 == "role")
         {
            this.roleMember(i0);
         }
      }
      
      private function roleMember(m0:MemberInfo) : void
      {
         this.roleMemberInfo = m0;
         var targetRoleId0:int = m0.getRoleID(this.unionData.getKingId());
         var meRoleId0:int = int(this.unionData.getMeRoleId());
         var str0:String = "";
         if(meRoleId0 < targetRoleId0)
         {
            UIOrder.alertError("你的职位不够高，无法进行此操作。");
         }
         else
         {
            if(targetRoleId0 > 0)
            {
               str0 = "是否要取消成员“" + ComMethod.color(this.roleMemberInfo.getNickName(),"#00FF00") + "”的军队职位？";
               str0 = ComMethod.color(str0,"#FF9900");
            }
            else
            {
               str0 = "是否要任命成员“" + ComMethod.color(this.roleMemberInfo.getNickName(),"#00FF00") + "”为军队管理员？";
               str0 = ComMethod.color(str0,"#00FFFF");
            }
            Gaming.uiGroup.alertBox.showNormal(str0,"yesAndNo",this.affter_roleMember);
         }
      }
      
      private function affter_roleMember() : void
      {
         var m0:MemberInfo = this.roleMemberInfo;
         var haveRoleB0:Boolean = m0.haveRoleB(Gaming.PG.da.union.nowUnion.uId);
         Gaming.uiGroup.connectUI.show();
         Gaming.api.union.member.setRole(Gaming.getSaveIndex(),m0.uId,m0.index,haveRoleB0 ? 0 : 1,this.yes_roleMember,this.no_roleMember);
      }
      
      private function yes_roleMember(bb0:Boolean) : void
      {
         var m0:MemberInfo = null;
         var haveRoleB0:Boolean = false;
         if(bb0)
         {
            Gaming.uiGroup.connectUI.hide();
            m0 = this.roleMemberInfo;
            haveRoleB0 = m0.haveRoleB(Gaming.PG.da.union.nowUnion.uId);
            m0.setRoleId(haveRoleB0 ? 0 : 1);
            Gaming.uiGroup.alertBox.showSuccess((haveRoleB0 ? "取消" : "设置") + "职位成功！");
            this.show();
         }
         else
         {
            this.no_roleMember("");
         }
      }
      
      private function no_roleMember(str0:String) : void
      {
         Gaming.uiGroup.connectUI.hide();
         Gaming.uiGroup.alertBox.showError("设置职位失败！\n" + str0);
      }
      
      private function removeMember(m0:MemberInfo) : void
      {
         var str0:String = null;
         var errorTip0:String = this.unionData.getRemoveErrorTip();
         if(errorTip0 != "")
         {
            Gaming.uiGroup.alertBox.showError(errorTip0);
         }
         else
         {
            this.removeMemberInfo = m0;
            str0 = "是否要踢出成员“" + ComMethod.color(this.removeMemberInfo.getNickName(),"#00FF00") + "”？\n剩余提示次数：" + ComMethod.color("3","#00FF00");
            str0 = ComMethod.color(str0,"#FF9900");
            Gaming.uiGroup.alertBox.showNormal(str0,"yesAndNo",this.affter_removeMember1);
         }
      }
      
      private function affter_removeMember1() : void
      {
         var str0:String = "是否要踢出成员“" + ComMethod.color(this.removeMemberInfo.getNickName(),"#00FF00") + "”？\n剩余提示次数：" + ComMethod.color("2","#00FF00");
         str0 = ComMethod.color(str0,"#FF9900");
         Gaming.uiGroup.alertBox.showNormal(str0,"yesAndNo",this.affter_removeMember2);
      }
      
      private function affter_removeMember2() : void
      {
         var str0:String = "是否要踢出成员“" + ComMethod.color(this.removeMemberInfo.getNickName(),"#00FF00") + "”？\n剩余提示次数：" + ComMethod.color("1","#00FF00");
         str0 = ComMethod.color(str0,"#FF9900");
         Gaming.uiGroup.alertBox.showNormal(str0,"yesAndNo",this.do_removeMember);
      }
      
      private function do_removeMember() : void
      {
         Gaming.uiGroup.connectUI.show();
         UIOrder.getStoreState(this.savePan_removeMember);
      }
      
      private function savePan_removeMember(v0:int) : void
      {
         if(v0 == 1 || v0 == -2)
         {
            Gaming.api.union.master.removeMember(Gaming.getSaveIndex(),this.removeMemberInfo.uId,this.removeMemberInfo.index,this.save_removeMember,this.no_removeMember);
         }
      }
      
      private function save_removeMember(bb0:Boolean) : void
      {
         if(bb0)
         {
            this.unionData.removeMemberEvent();
            UIOrder.yesSaveTip = "踢出成功！\n你今天还可以踢出" + this.unionData.getCanRemoveNum() + "个成员。";
            UIOrder.save(true,false,false,this.yes_removeMember);
         }
         else
         {
            this.no_removeMember("");
         }
      }
      
      private function yes_removeMember(v0:* = null) : void
      {
         Gaming.uiGroup.connectUI.hide();
         this.show();
      }
      
      private function no_removeMember(str0:String) : void
      {
         Gaming.uiGroup.connectUI.hide();
         Gaming.uiGroup.alertBox.showError("踢出失败！\n" + str0);
      }
      
      private function checkBtnClick(e:MouseEvent) : void
      {
         if(!this.checkBoard.visible)
         {
            this.checkBoard.show();
         }
         else
         {
            this.checkBoard.hide();
         }
      }
      
      private function conditionBtnClick(e:MouseEvent) : void
      {
         if(!this.conditionBoard.visible)
         {
            this.conditionBoard.show();
         }
         else
         {
            this.conditionBoard.hide();
         }
      }
      
      private function battleBtnClick(e:MouseEvent) : void
      {
         var s0:String = null;
         if(Boolean(this.unionData.nowMemberList))
         {
            s0 = this.unionData.nowMemberList.getAllCopyStr();
            System.setClipboard(s0);
            Gaming.uiGroup.alertBox.showSuccess("本周成员表格数据已复制到剪贴板。");
         }
         else
         {
            Gaming.uiGroup.alertBox.showError("数据不存在！");
         }
      }
      
      public function outLoginEvent() : void
      {
         this.removeMemberInfo = null;
         this.roleMemberInfo = null;
      }
      
      public function mouseUp(e:MouseEvent) : void
      {
         if(visible)
         {
            this.conditionBoard.mouseUp(e);
         }
      }
   }
}
