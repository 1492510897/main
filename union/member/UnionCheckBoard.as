package UI.union.member
{
   import UI.bag.ItemsGrid;
   import UI.base.NormalUI;
   import UI.base.button.*;
   import UI.base.event.*;
   import UI.base.page.*;
   import UI.top.*;
   import com.sounto.oldUtils.*;
   import dataAll._app.union.UnionData;
   import dataAll._app.union.info.*;
   import flash.display.MovieClip;
   import flash.display.SimpleButton;
   import flash.display.Sprite;
   import flash.events.*;
   
   public class UnionCheckBoard extends NormalUI
   {
       
      
      private var barTag:Sprite;
      
      private var pageTag:Sprite;
      
      private var closeBtn:SimpleButton;
      
      private var refuseBtnSp:MovieClip;
      
      private var conditionBtnSp:MovieClip;
      
      private var refuseBtn:NormalBtn;
      
      private var conditionBtn:NormalBtn;
      
      private var maxBarNum:int = 10;
      
      private var nowPage:int = 0;
      
      private var topBox:TopBarBox;
      
      private var pageBox:PageBox;
      
      private var btnArr:Array;
      
      private var nowAuditMemberInfo:MemberInfo;
      
      private var nowAuditLabel:String = "";
      
      private var conditionRefuseNum:int = 0;
      
      public function UnionCheckBoard()
      {
         this.refuseBtn = new NormalBtn();
         this.conditionBtn = new NormalBtn();
         this.topBox = new TopBarBox();
         this.pageBox = new PageBox();
         this.btnArr = [];
         super();
      }
      
      override public function setImg(img0:Sprite) : void
      {
         var list0:MemberCheckBarBtnList = null;
         elementNameArr = ["barTag","pageTag","closeBtn","refuseBtnSp","conditionBtnSp"];
         super.setImg(img0);
         this.initBar();
         for(var i:int = 0; i < this.maxBarNum; i++)
         {
            list0 = new MemberCheckBarBtnList();
            list0.setImg(Gaming.swfLoaderManager.getResource("UnionUI","checkBarBtnList"));
            list0.index = i;
            list0.clickFun = this.barBtnClick;
            this.btnArr.push(list0);
            addChild(list0);
            list0.visible = false;
         }
         this.closeBtn.addEventListener(MouseEvent.CLICK,this.closeClick);
         addChild(this.refuseBtn);
         this.refuseBtn.setImg(this.refuseBtnSp);
         this.refuseBtn.setName("全部拒绝");
         this.refuseBtn.addEventListener(MouseEvent.CLICK,this.btnClick);
         addChild(this.conditionBtn);
         this.conditionBtn.setImg(this.conditionBtnSp);
         this.conditionBtn.setName("根据条件拒绝");
         this.conditionBtn.addEventListener(MouseEvent.CLICK,this.btnClick);
      }
      
      private function initBar() : void
      {
         this.topBox.initTitle("UnionUI/checkBar",0);
         this.topBox.arg.init(1,this.maxBarNum,0,0);
         this.barTag.addChild(this.topBox);
         this.pageBox.setToNormalBtn();
         this.pageTag.addChild(this.pageBox);
         this.pageBox.setMaxPageShow(UnionListInfo.BAR_NUM);
         this.pageBox.setPageNumOut(1);
         this.pageBox.addEventListener(ClickEvent.ON_SHOW_PAGE,this.pageClick);
         this.pageBox.fleshPagePosition();
      }
      
      override public function show() : void
      {
         super.show();
         this.fleshData();
         this.getRankList(this.nowPage);
      }
      
      override protected function SET(str0:String, value0:Object) : void
      {
         if(!this[str0])
         {
            this[str0] = value0;
         }
      }
      
      private function get unionData() : UnionData
      {
         return Gaming.PG.da.union;
      }
      
      private function fleshData() : void
      {
      }
      
      private function getRankList(page0:int) : void
      {
         this.nowPage = page0;
         Gaming.uiGroup.connectUI.show("获取申请人数据……");
         Gaming.api.union.master.getApplyList(Gaming.getSaveIndex(),page0 + 1,this.maxBarNum,this.yes_getRankList,this.no_getRankList);
      }
      
      private function yes_getRankList(json0:String) : void
      {
         var u0:MemberCheckListInfo = MemberCheckListInfo.getByJson(json0);
         this.topBox.inData(u0);
         this.fleshBtnListByBar();
         this.refuseBtn.visible = this.topBox.gripArr.length > 0;
         this.conditionBtn.visible = this.refuseBtn.visible;
         this.pageBox.setPageNumOut(u0.getPageNum());
         this.pageBox.fleshPagePosition();
         Gaming.uiGroup.connectUI.hide();
      }
      
      private function no_getRankList(str0:String = "") : void
      {
         Gaming.uiGroup.alertBox.showNormal("获取申请人数据失败！\n" + str0,"yes",null,null,"no");
         Gaming.uiGroup.connectUI.hide();
      }
      
      private function pageClick(e:ClickEvent) : void
      {
         this.getRankList(e.index);
      }
      
      private function showPage(num0:int) : void
      {
         this.pageBox.showPage(num0);
      }
      
      private function fleshBtnListByBar() : void
      {
         var n:* = undefined;
         var list0:MemberCheckBarBtnList = null;
         var bar0:TopBar = null;
         for(n in this.btnArr)
         {
            list0 = this.btnArr[n];
            bar0 = this.topBox.gripArr[n];
            if(Boolean(bar0))
            {
               list0.visible = true;
               list0.itemsData = bar0.itemsData as MemberInfo;
               list0.x = bar0.x + this.barTag.x;
               list0.y = bar0.y + this.barTag.y;
            }
            else
            {
               list0.visible = false;
            }
         }
      }
      
      private function barClick(e:ClickEvent) : void
      {
      }
      
      private function closeClick(e:MouseEvent) : void
      {
         hide();
         Gaming.uiGroup.unionUI.outShowBox("member");
      }
      
      private function barBtnClick(u0:MemberInfo, label0:String) : void
      {
         this.nowAuditMemberInfo = u0;
         this.nowAuditLabel = label0;
         var str2:String = label0 == "accept" ? ComMethod.color("接受","#00FF00") : ComMethod.color("拒绝","#FF0000");
         Gaming.uiGroup.alertBox.showNormal("是否" + str2 + ComMethod.color("“" + u0.nickName + "”","#FFFF00") + "的申请？","yesAndNo",this.affter_auditMember);
      }
      
      private function affter_auditMember() : void
      {
         var u0:MemberInfo = this.nowAuditMemberInfo;
         Gaming.uiGroup.connectUI.show();
         Gaming.api.union.master.auditMember(Gaming.getSaveIndex(),u0.uId,u0.index,this.nowAuditLabel == "accept" ? 1 : 0,this.yes_auditMember,this.no_auditMember);
      }
      
      private function yes_auditMember(bb0:Boolean) : void
      {
         var grip0:NormalBtn = null;
         var btn0:MemberCheckBarBtnList = null;
         Gaming.uiGroup.connectUI.hide();
         if(bb0)
         {
            grip0 = this.topBox.findGripByData(this.nowAuditMemberInfo);
            if(Boolean(grip0))
            {
               btn0 = this.btnArr[grip0.index];
               if(Boolean(btn0))
               {
                  btn0.visible = false;
               }
            }
         }
         else
         {
            this.no_auditMember("审核失败！");
         }
      }
      
      private function no_auditMember(str0:String) : void
      {
         Gaming.uiGroup.connectUI.hide();
         Gaming.uiGroup.alertBox.showError(str0);
      }
      
      protected function btnClick(e:MouseEvent) : void
      {
         var btn0:NormalBtn = e.target as NormalBtn;
         if(btn0.actived)
         {
            if(btn0 == this.refuseBtn)
            {
               Gaming.uiGroup.alertBox.showNormal("是否拒绝当前页面内所有未处理的玩家申请？","yesAndNo",this.affter_refuse);
            }
            else if(btn0 == this.conditionBtn)
            {
               this.conditionRefuse();
            }
         }
      }
      
      private function affter_refuse() : void
      {
         var n:* = undefined;
         var grip0:ItemsGrid = null;
         var u0:MemberInfo = null;
         var obj0:Object = null;
         var btnList0:MemberCheckBarBtnList = null;
         var usersAry0:Array = [];
         for(n in this.topBox.gripArr)
         {
            grip0 = this.topBox.gripArr[n];
            u0 = grip0.itemsData as MemberInfo;
            obj0 = {};
            btnList0 = this.btnArr[n];
            if(Boolean(btnList0))
            {
               if(btnList0.visible)
               {
                  obj0.uid = u0.uId;
                  obj0.index = u0.index;
               }
            }
            usersAry0.push(obj0);
         }
         Gaming.uiGroup.connectUI.show();
         Gaming.api.union.master.applyMultiAudit(Gaming.getSaveIndex(),usersAry0,0,this.yes_refuse,this.no_refuse);
      }
      
      private function yes_refuse(bb0:Boolean) : void
      {
         if(bb0)
         {
            Gaming.uiGroup.alertBox.showSuccess("操作成功！");
            this.showPage(0);
         }
         else
         {
            this.no_refuse("");
         }
      }
      
      private function no_refuse(str0:String) : void
      {
         Gaming.uiGroup.connectUI.hide();
         Gaming.uiGroup.alertBox.showError("审核错误。\n" + str0);
      }
      
      private function conditionRefuse() : void
      {
         var tip0:String = "是否拒绝本页内不符合以下收人条件的玩家？";
         tip0 += "\n" + this.unionData.nowUnion.getApplyConditionTip();
         Gaming.uiGroup.alertBox.showChoose(tip0,this.after_conditionRefuse);
      }
      
      private function after_conditionRefuse() : void
      {
         var n:* = undefined;
         var grip0:ItemsGrid = null;
         var u0:MemberInfo = null;
         var btnList0:MemberCheckBarBtnList = null;
         var obj0:Object = null;
         var usersAry0:Array = [];
         for(n in this.topBox.gripArr)
         {
            grip0 = this.topBox.gripArr[n];
            u0 = grip0.itemsData as MemberInfo;
            btnList0 = this.btnArr[n];
            if(Boolean(btnList0))
            {
               if(btnList0.visible)
               {
                  u0 = grip0.itemsData as MemberInfo;
                  if(!this.unionData.nowUnion.panApplyConditionInfo(u0))
                  {
                     obj0 = {};
                     obj0.uid = u0.uId;
                     obj0.index = u0.index;
                     usersAry0.push(obj0);
                  }
               }
            }
         }
         if(usersAry0.length > 0)
         {
            this.conditionRefuseNum = usersAry0.length;
            Gaming.uiGroup.connectUI.show();
            Gaming.api.union.master.applyMultiAudit(Gaming.getSaveIndex(),usersAry0,0,this.yes_conditionRefuse,this.no_conditionRefuse);
         }
         else
         {
            Gaming.uiGroup.alertBox.showError("没找到不符合条件的申请者。");
         }
      }
      
      private function yes_conditionRefuse(bb0:Boolean) : void
      {
         if(bb0)
         {
            Gaming.uiGroup.alertBox.showSuccess("操作成功！拒绝了" + this.conditionRefuseNum + "个申请者。");
            this.showPage(0);
         }
         else
         {
            this.no_refuse("");
         }
      }
      
      private function no_conditionRefuse(str0:String) : void
      {
         Gaming.uiGroup.connectUI.hide();
         Gaming.uiGroup.alertBox.showError("审核错误。\n" + str0);
      }
      
      public function outLoginEvent() : void
      {
         this.nowAuditLabel = "";
         this.nowAuditMemberInfo = null;
      }
   }
}
