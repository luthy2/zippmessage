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

  $scope.dissmissMessage = function(messageId){
    alert('Message Id is ' + messageId)
    };
});
