package UI.union.member
{
   import UI.base.AutoNormalUI;
   import UI.base.button.*;
   import com.sounto.utils.*;
   import dataAll._app.union.extra.UnionExtra;
   import dataAll._app.union.info.UnionInfo;
   import dataAll._app.vip.define.VipLevelDefine;
   import flash.display.Sprite;
   import flash.events.*;
   import flash.text.TextField;
   
   public class UnionConditionBoard extends AutoNormalUI
   {
       
      
      private var dpsTxt:TextField;
      
      private var vipTxt:TextField;
      
      private var closeBtn:NormalBtn;
      
      private var yesBtn:NormalBtn;
      
      public function UnionConditionBoard()
      {
         super();
         mcTypeArr = ["btnSp","txt"];
      }
      
      override public function setImg(img0:Sprite) : void
      {
         super.setImg(img0);
         this.yesBtn.setName("确定修改");
         this.dpsTxt.addEventListener(Event.CHANGE,this.dpsTxtChange);
         this.dpsTxt.maxChars = 15;
         this.vipTxt.addEventListener(Event.CHANGE,this.vipTxtChange);
         this.vipTxt.maxChars = 2;
      }
      
      override protected function SET(str0:String, value0:Object) : void
      {
         if(!this[str0])
         {
            this[str0] = value0;
         }
      }
      
      override protected function GET(str0:String) : *
      {
         return this[str0];
      }
      
      override public function show() : void
      {
         if(Boolean(this.unionInfo))
         {
            super.show();
            this.fleshBySave();
         }
      }
      
      override protected function btnClick(e:MouseEvent) : void
      {
         var btn0:NormalBtn = e.target as NormalBtn;
         var funName0:String = btn0.label + "BtnClick";
         this[funName0](e);
      }
      
      private function get unionInfo() : UnionInfo
      {
         return Gaming.PG.da.union.nowUnion;
      }
      
      private function fleshBySave() : void
      {
         var extra0:UnionExtra = this.unionInfo.extraObj;
         this.dpsTxt.text = extra0.dpsLimit + "";
         this.vipTxt.text = extra0.vipLimit + "";
      }
      
      public function mouseUp(e:MouseEvent) : void
      {
         if(this.dpsTxt.text == "")
         {
            this.fleshDps();
         }
         if(this.vipTxt.text == "")
         {
            this.fleshVip();
         }
      }
      
      private function dealNumber(s0:String) : Number
      {
         var v0:Number = Number(s0);
         if(isNaN(v0))
         {
            v0 = 0;
         }
         if(v0 < 0)
         {
            v0 = 0;
         }
         return Number(NumberMethod.toFixed(v0,0));
      }
      
      private function dpsTxtChange(e:Event) : void
      {
         this.fleshDps(true);
      }
      
      private function fleshDps(spaceB0:Boolean = false) : Number
      {
         var s0:String = this.dpsTxt.text;
         var v0:Number = Number(this.dealNumber(s0));
         if(s0 != "" || !spaceB0)
         {
            s0 = v0 + "";
         }
         this.dpsTxt.text = s0;
         return v0;
      }
      
      private function vipTxtChange(e:Event) : void
      {
         this.fleshVip(true);
      }
      
      private function fleshVip(spaceB0:Boolean = false) : Number
      {
         var s0:String = this.vipTxt.text;
         var v0:Number = Number(this.dealNumber(s0));
         var maxD0:VipLevelDefine = Gaming.defineGroup.vip.getMaxLevelDefine();
         if(v0 > maxD0.getTrueLevel())
         {
            v0 = maxD0.getTrueLevel();
         }
         if(s0 != "" || !spaceB0)
         {
            s0 = v0 + "";
         }
         this.vipTxt.text = s0;
         return v0;
      }
      
      private function yesBtnClick(e:MouseEvent) : void
      {
         var extra0:UnionExtra = this.unionInfo.extraObj;
         extra0.dpsLimit = this.fleshDps();
         extra0.vipLimit = this.fleshVip();
         this.unionInfo.refreshToExtra();
         Gaming.uiGroup.unionUI.flesher.fleshUnionInfo(this.yesChange);
      }
      
      private function yesChange(data:*) : void
      {
         hide();
         Gaming.uiGroup.alertBox.showSuccess("修改收人条件成功！");
      }
      
      private function closeBtnClick(e:MouseEvent) : void
      {
         hide();
      }
   }
}
