'use strict'

var zippApp = angular.module("zippApp", []);

zippApp.controller("InboxController", function InboxController($scope, $http, $q){
  $scope.inbox = []
    $http ({
      method: 'GET',
      url: 'http://zippmessage-staging.herokuapp.com/api/1/user/inbox'
    }).then(function success(response){
      console.log(response)
      $scope.inbox = response.data
    }), function error(response){
      console.log(response)
    };

  $scope.bookmarkMessage = function(messageId){
      $http ({
        method: 'GET',
        url: 'http://zippmessage-staging.herokuapp.com/api/1/bookmark/'+messageId
      }).then(function success(response){
        console.log(response)
      }), function error(response){
        console.log(response)
      };
    };

  $scope.dismissMessage = function(messageId){
    console.log('Message Id is ' + messageId);
    for (var i = 0; i < $scope.inbox.length; i++){
      if ($scope.inbox[i].id == messageId){
        $scope.inbox.splice(i,1);
        break
      }
    }
  };
});
