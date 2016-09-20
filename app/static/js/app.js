'use strict'

var zippApp = angular.module("zippApp", []);

zippApp.controller("InboxController", function InboxController($scope, $http, $q, $sce, $timeout){
  $scope.loading = true;
  $scope.alert = '';
  $scope.$sce = $sce;
  $scope.loadedAll = false;
  $scope.inbox = []
  $scope.bookmarks = []
    var api_base="http://www.zippmsg.com/api/1/"
    $http ({
      method: 'GET',
      url: api_base + 'user/inbox'
    }).then(function success(response){
      console.log(response)
      $scope.inbox = response.data
      $scope.loading = false;
      if (response.data.length < 6){
        $scope.loadedAll = true;
      }
    }), function error(response){
      console.log(response)
    };
    //
    // $http({
    //   method:'GET',
    //   url: api_base + 'user/bookmarks'
    // }).then(function success(response){
    //   console.log(response)
    //   $scope.bookmarks = response.data
    // })

  $scope.getInbox = function(){
    $scope.loading = true;
    $http ({
      method:'GET',
      url: api_base + 'user/inbox',
      params: {'offset':$scope.inbox.length}
    }).then(function success(response){
      console.log(response)
      $scope.inbox = $scope.inbox.concat(response.data)
      $scope.loading = false;
      console.log($scope.inbox)
      if (response.data.length < 6){
        $scope.loadedAll = true;
      }
    }), function error(response){
      $scope.loading = false;
      $scope.alert = "We're having problems loading your inbox. Try again in a few minutes."
      console.log(response);
    };
  };

  $scope.bookmarkMessage = function(messageId){
      $http ({
        method: 'GET',
        url: 'http://www.zippmsg.com/api/1/bookmark/'+messageId
      }).then(function success(response){
        console.log(response)
        for (var i = 0; i < $scope.inbox.length; i++){
          if ($scope.inbox[i].id == messageId){
            $scope.inbox.splice(i,1);
            break
          }
        }
    }), function error(response){
        console.log(response)
        $scope.alert = 'Something went wrong, we couldnt bookmark this!'
      };
    };

  $scope.dismissMessage = function(messageId){
    $http ({
      method: 'GET',
      url: api_base+'dismiss/'+messageId
    }).then(function success(response){
        console.log(response)
        for (var i = 0; i < $scope.inbox.length; i++){
          if ($scope.inbox[i].id == messageId){
            $scope.inbox.splice(i,1);
            break
        }
      }
        $scope.alert = 'Message Dismissed'
        $timeout(function(){
            $scope.alert ='';
        }, 2800);
    }), function error(response){
      console.log(response)
      $scope.alert = 'hmmm... something went wrong and we were unable to dismiss the message.'
    };
  };
  $scope.createReaction = function(messageId, action){
    reaction = "reacted: "+action+" to"
    $http ({
      method: 'POST',
      url: api_base+'activity/create',
      data:{ "message_id":messageId, "action":reaction }
    }).then(function success(response){
        console.log(response)
        $scope.alert = 'Reaction ' + action + 'Sent!'
        $timeout(function(){
            $scope.alert ='';
        }, 2800);
    }), function error(response){
      console.log(response)
      $scope.alert = response.error
    };
  };

  // $scope.createMessage = function(){
  //   $http({
  //     method: 'POST',
  //     url:'http://zippmessage-staging.herokuapp.com/api/1/create/message',
  //     data:{
  //
  //     }
  //   })
  // }

});





// zippApp.config(['$locationProvider', '$routeProvider', function config($locationProvider, $routeProvider){
//   $locationProvider.hashPrefix('!');
//
//   $routeProvider
//     .when(
//       '/app/inbox', {
//         template: '<inbox></inbox>'
//       })
//     .when(
//       '/app/bookmarks',{
//         template: '<bookmarks></bookmarks>'
//       })
//     .otherwise({
//         redirectTo: '/app/inbox'
//       })
// }])
// ;
