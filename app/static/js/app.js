'use strict'

var zippApp = angular.module("zippApp", []);

zippApp.controller("InboxController", function InboxController($scope, $http, $q){
  $scope.inbox = [
    $http ({
      method: 'GET',
      url: 'http://zippmessage-staging.herokuapp.com/api/1/heartbeat'
    }).then(function success(response){
      console.log(response)
    }), function error(response){
      console.log(response)
    }
  ];
});
