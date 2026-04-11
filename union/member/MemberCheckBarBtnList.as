package UI.union.member
{
   import UI.base.btnList.BtnBox;
   import UI.base.button.*;
   import dataAll._app.union.info.MemberInfo;
   import flash.display.Sprite;
   import flash.events.MouseEvent;
   
   public class MemberCheckBarBtnList extends BtnBox
   {
       
      
      public var itemsData:MemberInfo;
      
      public var index:int = 0;
      
      public var clickFun:Function;
      
      public function MemberCheckBarBtnList()
      {
         super();
      }
      
      override public function setImg(img0:Sprite) : void
      {
         super.setImg(img0);
         getBtn("accept").setName("通过");
         getBtn("refuse").setName("拒绝");
      }
      
      override protected function btnClick(e:MouseEvent) : void
      {
         var btn0:NormalBtn = e.target as NormalBtn;
         if(this.clickFun is Function)
         {
            this.clickFun(this.itemsData,btn0.label);
         }
      }
   }
}
