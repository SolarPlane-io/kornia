import torch
import torch.nn as nn
import torch.nn.functional as F

from kornia.filters.kernels import get_spatial_gradient_kernel2d, get_spatial_gradient_kernel3d
from kornia.filters.kernels import normalize_kernel2d


class SpatialGradient(torch.nn.Module):
    r"""Computes the first order image derivative in both x and y using a Sobel or Scharr
    operator.

    Return:
        torch.Tensor: the sobel edges of the input feature map.

    Shape:
        - Input: :math:`(B, C, H, W)`
        - Output: :math:`(B, C, 2, H, W)`

    Examples:
        input = torch.rand(1, 3, 4, 4)
        output = kornia.filters.SpatialGradient()(input)  # 1x3x2x4x4
    """

    def __init__(self,
                 mode: str = 'sobel',
                 order: int = 1,
                 normalized: bool = True,
                 coord: str = "xy",
                 device: str = "cpu",
                 dtype: torch.dtype = torch.float) -> None:
        super(SpatialGradient, self).__init__()
        self.normalized: bool = normalized
        self.order: int = order
        self.mode: str = mode
        self.kernel: torch.Tensor = get_spatial_gradient_kernel2d(mode, order, coord)
        if self.normalized:
            self.kernel = normalize_kernel2d(self.kernel)
        # Pad with "replicate for spatial dims, but with zeros for channel
        self.spatial_pad = [self.kernel.size(1) // 2,
                            self.kernel.size(1) // 2,
                            self.kernel.size(2) // 2,
                            self.kernel.size(2) // 2]
        # Prepare kernel
        self.kernel: torch.Tensor = self.kernel.to(device).to(dtype).detach()
        self.kernel: torch.Tensor = self.kernel.unsqueeze(1).unsqueeze(1)
        self.kernel: torch.Tensor = self.kernel.flip(-3)
        return

    def __repr__(self) -> str:
        return self.__class__.__name__ + '('\
            'order=' + str(self.order) + ', ' + \
            'normalized=' + str(self.normalized) + ', ' + \
            'mode=' + self.mode + ')'

    def forward(self, inp: torch.Tensor) -> torch.Tensor:  # type: ignore
        if not torch.is_tensor(inp):
            raise TypeError("Input type is not a torch.Tensor. Got {}"
                            .format(type(inp)))
        if not len(inp.shape) == 4:
            raise ValueError("Invalid input shape, we expect BxCxHxW. Got: {}"
                             .format(inp.shape))
        # prepare kernel
        b, c, h, w = inp.shape

        # convolve inp tensor with sobel kernel
        out_channels: int = 3 if self.order == 2 else 2
        padded_inp: torch.Tensor = torch.nn.functional.pad(inp.reshape(b * c, 1, h, w),
                                                           self.spatial_pad, 'replicate')[:, :, None]
        return torch.nn.functional.conv3d(padded_inp, self.kernel, padding=0).view(b, c, out_channels, h, w)


class SpatialGradient3d(nn.Module):
    r"""Computes the first and second order volume derivative in x, y and d using a diff
    operator.

    Return:
        torch.Tensor: the spatial gradients of the input feature map.

    Shape:
        - Input: :math:`(B, C, D, H, W)`. D, H, W are spatial dimensions, gradient is calculated w.r.t to them.
        - Output: :math:`(B, C, 3, D, H, W)` or :math:`(B, C, 6, D, H, W)`

    Examples:
        >>> input = torch.rand(1, 3, 4, 4)
        >>> output = kornia.filters.SpatialGradient()(input)  # 1x3x2x4x4
    """

    def __init__(self,
                 mode: str = 'diff',
                 order: int = 1) -> None:
        super(SpatialGradient3d, self).__init__()
        self.order: int = order
        self.mode: str = mode
        self.kernel = get_spatial_gradient_kernel3d(mode, order)
        return

    def __repr__(self) -> str:
        return self.__class__.__name__ + '('\
            'order=' + str(self.order) + ', ' + \
            'mode=' + self.mode + ')'

    def forward(self, input: torch.Tensor) -> torch.Tensor:  # type: ignore
        if not torch.is_tensor(input):
            raise TypeError("Input type is not a torch.Tensor. Got {}"
                            .format(type(input)))
        if not len(input.shape) == 5:
            raise ValueError("Invalid input shape, we expect BxCxDxHxW. Got: {}"
                             .format(input.shape))
        # prepare kernel
        b, c, d, h, w = input.shape
        tmp_kernel: torch.Tensor = self.kernel.to(input.device).to(input.dtype).detach()
        kernel: torch.Tensor = tmp_kernel.repeat(c, 1, 1, 1, 1)

        # convolve input tensor with grad kernel
        kernel_flip: torch.Tensor = kernel.flip(-3)
        # Pad with "replicate for spatial dims, but with zeros for channel
        spatial_pad = [self.kernel.size(2) // 2,
                       self.kernel.size(2) // 2,
                       self.kernel.size(3) // 2,
                       self.kernel.size(3) // 2,
                       self.kernel.size(4) // 2,
                       self.kernel.size(4) // 2]
        out_ch: int = 6 if self.order == 2 else 3
        return F.conv3d(F.pad(input, spatial_pad, 'replicate'), kernel, padding=0, groups=c).view(b, c, out_ch, d, h, w)


class Sobel(nn.Module):
    r"""Computes the Sobel operator and returns the magnitude per channel.

    Return:
        torch.Tensor: the sobel edge gradient maginitudes map.

    Args:
        normalized (bool): if True, L1 norm of the kernel is set to 1.

    Shape:
        - Input: :math:`(B, C, H, W)`
        - Output: :math:`(B, C, H, W)`

    Examples:
        >>> input = torch.rand(1, 3, 4, 4)
        >>> output = kornia.filters.Sobel()(input)  # 1x3x4x4
    """

    def __init__(self,
                 normalized: bool = True) -> None:
        super(Sobel, self).__init__()
        self.normalized: bool = normalized

    def __repr__(self) -> str:
        return self.__class__.__name__ + '('\
            'normalized=' + str(self.normalized) + ')'

    def forward(self, input: torch.Tensor) -> torch.Tensor:  # type: ignore
        if not torch.is_tensor(input):
            raise TypeError("Input type is not a torch.Tensor. Got {}"
                            .format(type(input)))
        if not len(input.shape) == 4:
            raise ValueError("Invalid input shape, we expect BxCxHxW. Got: {}"
                             .format(input.shape))
        # comput the x/y gradients
        edges: torch.Tensor = spatial_gradient(input,
                                               normalized=self.normalized)

        # unpack the edges
        gx: torch.Tensor = edges[:, :, 0]
        gy: torch.Tensor = edges[:, :, 1]

        # compute gradient maginitude
        magnitude: torch.Tensor = torch.sqrt(gx * gx + gy * gy)
        return magnitude


# functiona api


def spatial_gradient(input: torch.Tensor,
                     mode: str = 'sobel',
                     order: int = 1,
                     normalized: bool = True) -> torch.Tensor:
    r"""Computes the first order image derivative in both x and y using a Sobel
    operator.

    See :class:`~kornia.filters.SpatialGradient` for details.
    """
    return SpatialGradient(mode, order, normalized)(input)


def spatial_gradient3d(input: torch.Tensor,
                       mode: str = 'diff',
                       order: int = 1) -> torch.Tensor:
    r"""Computes the first or second order image derivative in both x and y and y using a diff
    operator.

    See :class:`~kornia.filters.SpatialGradient3d` for details.
    """
    return SpatialGradient3d(mode, order)(input)


def sobel(input: torch.Tensor, normalized: bool = True) -> torch.Tensor:
    r"""Computes the Sobel operator and returns the magnitude per channel.

    See :class:`~kornia.filters.Sobel` for details.
    """
    return Sobel(normalized)(input)
