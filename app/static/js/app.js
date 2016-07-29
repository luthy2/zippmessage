'use strict'

var zippApp = angular.module("zippApp", []);

zippApp.controller("InboxController", function InboxController($scope, $http, $q, $sce, $timeout){
  $scope.alert = '';
  $scope.$sce = $sce;
  $scope.loadedAll = false;
  $scope.inbox = []
    $http ({
      method: 'GET',
      url: 'http://zippmessage-staging.herokuapp.com/api/1/user/inbox'
    }).then(function success(response){
      console.log(response)
      $scope.inbox = response.data
      if (response.data.length < 6){
        $scope.loadedAll = true;
      }
    }), function error(response){
      console.log(response)
    };

  $scope.getInbox = function(){
    $scope.loading = true;
    $http ({
      method:'GET',
      url:'http://zippmessage-staging.herokuapp.com/api/1/user/inbox',
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
      console.log(response);
    };
  };

  $scope.bookmarkMessage = function(messageId){
      $http ({
        method: 'GET',
        url: 'http://zippmessage-staging.herokuapp.com/api/1/bookmark/'+messageId
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
        alert('something went wrong, we couldnt bookmark this!')
      };
    };

  $scope.dismissMessage = function(messageId){
    $http ({
      method: 'GET',
      url: 'http://zippmessage-staging.herokuapp.com/api/1/dismiss/'+messageId
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
      alert('hmmm... something went wrong and we were unable to dismiss the message.')
      $scope.alert = 'hmmm... something went wrong and we were unable to dismiss the message.'
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
