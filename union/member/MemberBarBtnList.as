package UI.union.member
{
   import UI.base.btnList.BtnBox;
   import UI.base.button.*;
   import com.sounto.oldUtils.*;
   import dataAll._app.union.UnionData;
   import dataAll._app.union.info.MemberInfo;
   import flash.display.Sprite;
   import flash.events.MouseEvent;
   
   public class MemberBarBtnList extends BtnBox
   {
       
      
      public var itemsData:MemberInfo;
      
      public var index:int = 0;
      
      public var clickFun:Function;
      
      public function MemberBarBtnList()
      {
         super();
      }
      
      override public function setImg(img0:Sprite) : void
      {
         super.setImg(img0);
         getBtn("expel").setName("踢出");
         getBtn("role").setName("任命");
      }
      
      override protected function btnClick(e:MouseEvent) : void
      {
         var btn0:NormalBtn = e.target as NormalBtn;
         if(this.clickFun is Function)
         {
            this.clickFun(this.itemsData,btn0.label);
         }
      }
      
      public function setVisible(union0:UnionData) : void
      {
         var isMeB0:Boolean = false;
         var kingUid0:Number = NaN;
         var meCanRoleB0:Boolean = false;
         var meHaveCheckRightB0:Boolean = false;
         var barIsKingB0:Boolean = false;
         var barHaveRoleB0:Boolean = false;
         if(Gaming.isLocal())
         {
            getBtn("expel").visible = true;
            getBtn("role").visible = true;
         }
         else
         {
            isMeB0 = this.itemsData.uId == union0.nowMember.uId;
            kingUid0 = union0.nowUnion.uId;
            meCanRoleB0 = union0.canSetRoleB();
            meHaveCheckRightB0 = union0.haveCheckRightB();
            barIsKingB0 = kingUid0 == this.itemsData.uId;
            barHaveRoleB0 = this.itemsData.haveRoleB(kingUid0);
            getBtn("expel").visible = meHaveCheckRightB0 && !isMeB0 && !barIsKingB0;
            if(union0.isAdminB() && this.itemsData.haveRoleID())
            {
               getBtn("expel").visible = false;
            }
            getBtn("role").visible = meCanRoleB0 && !isMeB0 && !barIsKingB0;
            getBtn("role").setName(barHaveRoleB0 ? ComMethod.color("撤职","#FFFF00") : "任命");
         }
      }
   }
}
