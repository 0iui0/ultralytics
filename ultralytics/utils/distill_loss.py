import torch
import torch.nn as nn
import torch.nn.functional as F

class MimicLoss(nn.Module):
    def __init__(self, channels_s, channels_t):
        super(MimicLoss, self).__init__()
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.mse = nn.MSELoss()
 
    def forward(self, y_s, y_t):
        """Forward computation.
        Args:
            y_s (list): The student model prediction with
                shape (N, C, H, W) in list.
            y_t (list): The teacher model prediction with
                shape (N, C, H, W) in list.
        Return:
            torch.Tensor: The calculated loss value of all stages.
        """
        assert len(y_s) == len(y_t)
        losses = []
        for idx, (s, t) in enumerate(zip(y_s, y_t)):
            assert s.shape == t.shape
            losses.append(self.mse(s, t))
        loss = sum(losses)
        return loss

class CWDLoss(nn.Module):
    """PyTorch version of `Channel-wise Distillation for Semantic Segmentation.
    <https://arxiv.org/abs/2011.13256>`_.
    """
 
    def __init__(self, channels_s, channels_t,tau=1.0):
        super(CWDLoss, self).__init__()
        self.tau = tau
 
    def forward(self, y_s, y_t):
        """Forward computation.
        Args:
            y_s (list): The student model prediction with
                shape (N, C, H, W) in list.
            y_t (list): The teacher model prediction with
                shape (N, C, H, W) in list.
        Return:
            torch.Tensor: The calculated loss value of all stages.
        """
        assert len(y_s) == len(y_t)
        losses = []
 
        for idx, (s, t) in enumerate(zip(y_s, y_t)):
 
            assert s.shape == t.shape
            
            N, C, H, W = s.shape
            
            # normalize in channel diemension
            softmax_pred_T = F.softmax(t.view(-1, W * H) / self.tau, dim=1)  # [N*C, H*W]
            
            logsoftmax = torch.nn.LogSoftmax(dim=1)
            cost = torch.sum(
                softmax_pred_T * logsoftmax(t.view(-1, W * H) / self.tau) - 
                softmax_pred_T * logsoftmax(s.view(-1, W * H) / self.tau)) * (self.tau ** 2)
 
            losses.append(cost / (C * N))
        loss = sum(losses)
 
        return loss

class MGDLoss(nn.Module):
    def __init__(self, channels_s, channels_t, alpha_mgd=0.00002, lambda_mgd=0.65):
        super(MGDLoss, self).__init__()
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.alpha_mgd = alpha_mgd
        self.lambda_mgd = lambda_mgd
 
        self.generation = [
            nn.Sequential(
                nn.Conv2d(channel, channel, kernel_size=3, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(channel, channel, kernel_size=3, padding=1)).to(device) for channel in channels_t
        ]
 
    def forward(self, y_s, y_t):
        """Forward computation.
        Args:
            y_s (list): The student model prediction with
                shape (N, C, H, W) in list.
            y_t (list): The teacher model prediction with
                shape (N, C, H, W) in list.
        Return:
            torch.Tensor: The calculated loss value of all stages.
        """
        assert len(y_s) == len(y_t)
        losses = []
        for idx, (s, t) in enumerate(zip(y_s, y_t)):
            assert s.shape == t.shape
            losses.append(self.get_dis_loss(s, t, idx) * self.alpha_mgd)
        loss = sum(losses)
        return loss
 
    def get_dis_loss(self, preds_S, preds_T, idx):
        loss_mse = nn.MSELoss(reduction='sum')
        N, C, H, W = preds_T.shape
 
        device = preds_S.device
        mat = torch.rand((N, 1, H, W)).to(device)
        mat = torch.where(mat > 1 - self.lambda_mgd, 0, 1).to(device)
 
        masked_fea = torch.mul(preds_S, mat)
        new_fea = self.generation[idx](masked_fea)
 
        dis_loss = loss_mse(new_fea, preds_T) / N
 
        return dis_loss    

class Distill_LogitLoss:
    def __init__(self,p, t_p, alpha =0.25):
        
        t_ft = torch.cuda.FloatTensor if t_p[0].is_cuda else torch.Tensor
        self.p =p
        self.t_p = t_p 
        self.logit_loss = t_ft([0])
        self.DLogitLoss = nn.MSELoss(reduction="none")
        self.bs = p[0].shape[0]
        self.alpha = alpha
    
    def __call__(self):
        # per output
        assert len(self.p) == len(self.t_p)
        for i, (pi,t_pi) in enumerate(zip(self.p,self.t_p)):  # layer index, layer predictions
            assert pi.shape == t_pi.shape
            self.logit_loss += torch.mean(self.DLogitLoss(pi, t_pi))
        return self.logit_loss[0]*self.alpha