"""
Bayesian Personalized Ranking

Matrix Factorization model and a variety of classes
implementing different sampling strategies.
"""
import sys
import numpy as np
from math import exp, log
import random
from sampling import UniformPairWithoutReplacement, UniformUserUniformItem


class BPRArgs(object):

    def __init__(self,learning_rate=0.05,
                 bias_regularization=1.0,
                 user_regularization=1.0,
                 positive_item_regularization=1.0,
                 negative_item_regularization=1.0,
                 update_negative_item_factors=True):
        self.learning_rate = learning_rate
        self.bias_regularization = bias_regularization
        self.user_regularization = user_regularization
        self.positive_item_regularization = positive_item_regularization
        self.negative_item_regularization = negative_item_regularization
        self.update_negative_item_factors = update_negative_item_factors


class BPR(object):

    def __init__(self,D,args):
        """initialize BPR matrix factorization model
        D: number of factors
        """
        self.D = D
        self.learning_rate = args.learning_rate
        self.bias_regularization = args.bias_regularization
        self.user_regularization = args.user_regularization
        self.positive_item_regularization = args.positive_item_regularization
        self.negative_item_regularization = args.negative_item_regularization
        self.update_negative_item_factors = args.update_negative_item_factors
        self.i=0

    def train(self, data, sampler, num_iters):
        """train model
        data: user-item matrix as a scipy sparse matrix
              users and items are zero-indexed
        """
        self.init(data)
        
        best_loss=-1
        
        losses=[]

        print 'initial loss = {0}'.format(self.auc())
        for it in xrange(num_iters):
            print 'starting iteration {0}'.format(it)
            for u,i,j in sampler.generate_samples(self.data):
                self.update_factors(u,i,j)
            loss = self.auc()
            losses.append(loss)
            # if loss > best_loss
            print 'iteration {0}: loss = {1}'.format(it, loss)
        return losses

    def init(self,data):
        self.data = data
        self.num_users,self.num_items = self.data.shape

        self.item_bias = np.zeros(self.num_items)
        self.user_factors = np.random.random_sample((self.num_users,self.D))
        self.item_factors = np.random.random_sample((self.num_items,self.D))

        self.create_loss_samples(data)

    #load pre-trained model from memory
    def load(self, item_bias, user_factors, item_factors):
      self.item_bias = item_bias
      self.user_factors = user_factors
      self.item_factors = item_factors

    #called once on initiation
    def create_loss_samples(self, data):
        # apply rule of thumb to decide num samples over which to compute loss
        num_loss_samples = int(100*self.num_users**0.5)

        print 'sampling {0} <user,item i,item j> triples...'.format(num_loss_samples)
        sampler = UniformUserUniformItem(True)
        self.loss_samples = [t for t in sampler.generate_samples(data, num_loss_samples)]

    def update_factors(self,u,i,j):
        """apply SGD update"""
        
        # xuij = xui - xuj
        # xuij = alpha + beta_u + beta_i + dot(gamma_U, gamma_I) - (alpha + beta_u + beta_j + dot(gamma_U, gamma_J))
        # xuij = beta_i - beta_j + dot(g_U, g_I) - dot(g_U, g_J)

        xuij = self.item_bias[i] - self.item_bias[j]
        xuij+= np.dot(self.user_factors[u], self.item_factors[i]) - np.dot(self.user_factors[u], self.item_factors[j])
        # print np.mean(self.user_factors),np.mean(self.item_factors)


        #when it should be very small numbers. 
        z = 1.0/(1.0+exp(xuij)) # term of the deriviative of xuij

        # update bias terms
        d = z - self.bias_regularization * self.item_bias[i]
        self.item_bias[i] += self.learning_rate * d
        
        d = -z - self.bias_regularization * self.item_bias[j]
        self.item_bias[j] += self.learning_rate * d

        #run the 3 partial deriviatives (2 variables: W & H)
        #update the user vector w = w + n(z * (item_i - item_j) - reg...)
        d = (self.item_factors[i]-self.item_factors[j])*z - self.user_regularization*self.user_factors[u]
        self.user_factors[u] += self.learning_rate*d
            
        #update the pos item factor: h = h+ n(z * w - reg..)
        d = self.user_factors[u]*z - self.positive_item_regularization*self.item_factors[i]
        self.item_factors[i] += self.learning_rate*d
            
        #update the pos item factor: h = h+ n(-z * w - reg..)
        d = -self.user_factors[u]*z - self.negative_item_regularization *self.item_factors[j]
        self.item_factors[j] += self.learning_rate*d
        
        self.i+=1

    #this is taking the loss w/o the ln 
    def loss(self):
        ranking_loss = 0;
        for u,i,j in self.loss_samples:
            x = self.predict(u,i) - self.predict(u,j)
            
            # ln (sig(xuij)) + reg
            # sig(xuij) + reg
            ranking_loss += 1.0/(1.0+np.exp(x))
            
        complexity = 0;
        for u,i,j in self.loss_samples:
            complexity += self.user_regularization * np.dot(self.user_factors[u],self.user_factors[u])
            complexity += self.positive_item_regularization * np.dot(self.item_factors[i],self.item_factors[i])
            complexity += self.negative_item_regularization * np.dot(self.item_factors[j],self.item_factors[j])
            complexity += self.bias_regularization * self.item_bias[i]**2
            complexity += self.bias_regularization * self.item_bias[j]**2

        return (ranking_loss + 0.5*complexity) / (len(self.loss_samples))
        
    #average of AUC for each user
    #TP / TP+FN
    def auc(self):
      scores = []
      
      for u,i,j in self.loss_samples:
        xui = self.predict(u, i)
        xuj = self.predict(u, j)
        
        score = 1 if xui>xuj else 0
        scores.append(score)
      
      auc = np.mean(scores)
            
      return auc
      
      
    def auc_w_sampler(self, test_set):
      AUC_u_test = []
      num_samples = 1200 # half the times
      print "num auc test samples: %d"%num_samples
      
      for u,i in enumerate(test_set):
        x_ui = self.predict(u, i);
        count_test = 0;
        _max=0

        #choose n random items to test against
        #maybe I should choose the same random j's ahead of time...
        for j in np.random.choice(self.data.shape[1], num_samples):#xrange(self.n_items):
          if self.data[u,j]:        #make sure it's not my positive items
            continue

          _max+=1
          x_uj = self.predict(u, j)
          if (x_ui > x_uj):
            count_test+=1
          
        AUC_u_test.append(1.0 * count_test / _max)
        
      AUC_test = np.mean(AUC_u_test)

      return AUC_test

    def predict(self,u,i):
        return self.item_bias[i] + np.dot(self.user_factors[u],self.item_factors[i])



if __name__ == '__main__':
  pass