var zippApp = angluar.module('zippApp', []);

zippApp.controller('InboxController', function InboxController($scope)){
  $scope.inbox = [
    {
      title:"A Really Interesting Article",
      url:"https://www.google.com",
      from_user:"@John",
      description:"This article details some really interesting information",
      note:"read this article!!"
    },{
      title:"A Cool Article",
      url:"https://www.twitter.com",
      from_user:"@Mike",
      description:"This article details some cool information",
      note:"cool article!!"
    }
  ]
}
